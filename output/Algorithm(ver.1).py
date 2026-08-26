"""
Algorithm(ver.1).py
===================
Robust BOCPDMS + HSMM + Student-t emission -> regime experts -> BMA -> fractional Kelly
-> risk gate -> paper execution 의 참조 구현입니다.

주의
----
- 교육·연구용 예시이며 실거래용 완제품이 아닙니다.
- 기본 실행은 합성 일봉 데이터를 사용하고 주문은 PaperBroker에만 기록합니다.
- 실제 운용 전 point-in-time 데이터, 거래비용, 체결, 원장 대사, 규제 및
  장애 대응을 별도로 구현하고 검증해야 합니다.

실행 예시
---------
    python "Algorithm(ver.1).py"
    python "Algorithm(ver.1).py" --csv prices.csv --initial-cash 1000000

CSV 필수 열: Date, Open, High, Low, Close, Volume
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
except ImportError as exc:  # pragma: no cover
    raise SystemExit("필수 패키지가 없습니다: pip install numpy pandas scikit-learn") from exc


LOGGER = logging.getLogger("regime_trader")
REGIMES = ("bull", "bear", "sideways")
EPS = 1e-12


# ---------------------------------------------------------------------------
# 설정과 공통 자료형
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    seed: int = 42
    horizon: int = 1
    min_train_rows: int = 252
    retrain_every: int = 63
    bocpd_max_run_length: int = 180
    hsmm_bull_median_duration: float = 80.0
    hsmm_bear_median_duration: float = 40.0
    hsmm_sideways_median_duration: float = 35.0
    hsmm_duration_sigma: float = 0.55
    cp_alert: float = 0.35
    bma_forgetting: float = 0.985
    bma_weight_floor: float = 0.01
    bma_weight_cap: float = 0.70
    kelly_fraction: float = 0.20
    max_long_weight: float = 0.80
    max_short_weight: float = 0.40
    annual_vol_target: float = 0.10
    max_daily_loss: float = 0.025
    max_drawdown: float = 0.12
    max_turnover_per_bar: float = 0.25
    no_trade_band: float = 0.02
    commission_bps: float = 1.0
    spread_bps: float = 2.0
    slippage_bps: float = 2.0
    uncertainty_z: float = 0.15
    variance_floor: float = 1e-6
    initial_cash: float = 100_000.0


@dataclass
class PredictiveDistribution:
    mean: float
    variance: float
    p_up: float
    valid: bool = True
    reason: str = ""


@dataclass
class RegimeEngineState:
    p_change: float
    expected_run_length: float
    hsmm_remaining_duration: float
    entropy: float
    regime_probabilities: Dict[str, float]
    new_regime_probabilities: Dict[str, float]
    most_likely_regime: str


@dataclass
class RiskDecision:
    target_weight: float
    approved: bool
    reason: str


@dataclass
class PortfolioState:
    cash: float
    units: float = 0.0
    equity: float = 0.0
    peak_equity: float = 0.0
    last_equity: float = 0.0
    kill_switch: bool = False


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    decisions: pd.DataFrame
    metrics: Dict[str, float]


# ---------------------------------------------------------------------------
# 데이터와 피처
# ---------------------------------------------------------------------------


def validate_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"필수 OHLCV 열이 없습니다: {missing}")

    df = frame.copy()
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="raise")
        df = df.set_index("Date")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Date 열 또는 DatetimeIndex가 필요합니다.")
    df = df.sort_index()
    if df.index.has_duplicates:
        raise ValueError("중복 타임스탬프가 있습니다.")
    df[required] = df[required].apply(pd.to_numeric, errors="coerce")
    if df[required].isna().any().any():
        raise ValueError("OHLCV에 결측값 또는 숫자가 아닌 값이 있습니다.")
    if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise ValueError("가격은 0보다 커야 합니다.")
    if (df["Volume"] < 0).any():
        raise ValueError("거래량은 음수가 될 수 없습니다.")
    return df


def make_synthetic_ohlcv(n: int = 1_500, seed: int = 42) -> pd.DataFrame:
    """Bull/Bear/Sideways 블록을 가진 재현 가능한 합성 데이터."""
    rng = np.random.default_rng(seed)
    regimes = np.resize(np.repeat([0, 2, 1, 2], [300, 180, 220, 200]), n)
    drift = np.choose(regimes, [0.0007, -0.0009, 0.0])
    vol = np.choose(regimes, [0.010, 0.018, 0.007])
    ret = drift + vol * rng.standard_normal(n)
    close = 100.0 * np.exp(np.cumsum(ret))
    overnight = rng.normal(0, 0.0025, n)
    open_ = close * np.exp(overnight)
    intraday = np.abs(rng.normal(0.006, 0.003, n))
    high = np.maximum(open_, close) * (1 + intraday)
    low = np.minimum(open_, close) * np.maximum(0.01, 1 - intraday)
    volume = rng.lognormal(14.0, 0.35, n).astype(int)
    index = pd.bdate_range("2018-01-02", periods=n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=index,
    )


def build_features(ohlcv: pd.DataFrame, horizon: int = 1) -> pd.DataFrame:
    """모든 rolling 계산은 현재 및 과거 데이터만 사용한다."""
    df = validate_ohlcv(ohlcv)
    close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]
    log_price = np.log(close)
    log_ret = log_price.diff()
    previous_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)

    f = pd.DataFrame(index=df.index)
    f["ret_1"] = log_ret
    for window in (5, 20, 60):
        f[f"ret_{window}"] = log_price.diff(window)
        f[f"vol_{window}"] = log_ret.rolling(window).std(ddof=0)
        f[f"ma_gap_{window}"] = close / close.rolling(window).mean() - 1.0
    f["ema_slope"] = close.ewm(span=12, adjust=False).mean().pct_change(5)
    f["atr_14"] = true_range.rolling(14).mean() / close
    f["downside_vol"] = log_ret.clip(upper=0).rolling(20).std(ddof=0)
    f["bollinger_z"] = (close - close.rolling(20).mean()) / (
        close.rolling(20).std(ddof=0) + EPS
    )
    f["bollinger_width"] = 4.0 * close.rolling(20).std(ddof=0) / close.rolling(20).mean()
    f["volume_z"] = (np.log1p(volume) - np.log1p(volume).rolling(20).mean()) / (
        np.log1p(volume).rolling(20).std(ddof=0) + EPS
    )
    f["range_pct"] = (high - low) / close
    f["target"] = log_price.shift(-horizon) - log_price
    f["next_open_return"] = np.log(df["Open"].shift(-1) / close)
    return f.replace([np.inf, -np.inf], np.nan)


FEATURE_COLUMNS = [
    "ret_1", "ret_5", "ret_20", "ret_60", "vol_5", "vol_20", "vol_60",
    "ma_gap_5", "ma_gap_20", "ma_gap_60", "ema_slope", "atr_14",
    "downside_vol", "bollinger_z", "bollinger_width", "volume_z", "range_pct",
]


# ---------------------------------------------------------------------------
# Robust BOCPDMS + HSMM + Student-t emission
# ---------------------------------------------------------------------------


class RobustBOCPDMSHSMM:
    """온라인 BOCPD model selection과 explicit-duration HSMM의 결합.

    - joint posterior p(regime, run_length | x_1:t)를 직접 유지한다.
    - 각 regime의 log-normal duration 분포가 run-length별 hazard를 만든다.
    - Normal-Inverse-Gamma conjugacy가 Student-t posterior predictive를 만들어
      fat-tail 관측 한 건이 변화점으로 과대 해석되는 현상을 완화한다.
    - 상태전이 행렬을 통해 변화 시점뿐 아니라 바뀌는 상태의 posterior도 낸다.

    관측값은 과거 정보만으로 표준화된 일간 로그수익률이다. 실전 확장 시
    multivariate Student-t 또는 copula emission으로 교체할 수 있다.
    """

    def __init__(
        self,
        max_run_length: int,
        duration_medians: Mapping[str, float],
        duration_sigma: float = 0.55,
    ):
        self.max_run_length = max_run_length
        self.states = REGIMES
        self.n_states = len(self.states)
        self.duration_medians = np.array([duration_medians[s] for s in self.states], dtype=float)
        self.duration_sigma = np.full(self.n_states, duration_sigma, dtype=float)

        # Bull/Bear는 Sideways를 거쳐 전환할 가능성을 높인 약한 구조적 prior다.
        self.transition = np.array(
            [
                [0.00, 0.25, 0.75],
                [0.25, 0.00, 0.75],
                [0.55, 0.45, 0.00],
            ],
            dtype=float,
        )
        self.state_prior = np.array([0.30, 0.25, 0.45], dtype=float)

        # NIG(mu, kappa, alpha, beta). 낮은 df의 predictive가 fat tail을 허용한다.
        self.prior_mu = np.array([0.30, -0.30, 0.0], dtype=float)
        # 상태 정체성이 장기 표본에 완전히 씻겨 나가지 않도록 informative prior를
        # 사용한다. 값은 표준화 수익률 기준이며 walk-forward calibration 대상이다.
        self.prior_kappa = np.array([25.0, 25.0, 40.0], dtype=float)
        self.prior_alpha = np.array([3.0, 3.0, 3.5], dtype=float)
        self.prior_beta = np.array([3.0, 3.0, 2.5], dtype=float)

        shape = (self.n_states, self.max_run_length + 1)
        self.joint = np.zeros(shape, dtype=float)
        self.mu = np.repeat(self.prior_mu[:, None], shape[1], axis=1)
        self.kappa = np.repeat(self.prior_kappa[:, None], shape[1], axis=1)
        self.alpha = np.repeat(self.prior_alpha[:, None], shape[1], axis=1)
        self.beta = np.repeat(self.prior_beta[:, None], shape[1], axis=1)
        self.initialized = False

    @staticmethod
    def _normal_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def _duration_cdf(self, state: int, duration: float) -> float:
        if duration <= 0:
            return 0.0
        z = (math.log(duration) - math.log(self.duration_medians[state])) / self.duration_sigma[state]
        return self._normal_cdf(z)

    def _hazard(self, state: int, run_length: int) -> float:
        """P(D=d | D>=d), d=run_length+1인 discrete log-normal hazard."""
        d = run_length + 1.0
        lower = self._duration_cdf(state, max(0.5, d - 0.5))
        upper = self._duration_cdf(state, d + 0.5)
        survival = max(1.0 - lower, EPS)
        hazard = (upper - lower) / survival
        if run_length >= self.max_run_length:
            return 0.999
        return float(np.clip(hazard, 0.0005, 0.95))

    @staticmethod
    def _student_t_pdf(x: float, mu: float, kappa: float, alpha: float, beta: float) -> float:
        degrees = max(2.0 * alpha, 2.01)
        scale2 = max(beta * (kappa + 1.0) / (alpha * kappa), 1e-8)
        log_density = (
            math.lgamma((degrees + 1.0) / 2.0)
            - math.lgamma(degrees / 2.0)
            - 0.5 * math.log(degrees * math.pi * scale2)
            - ((degrees + 1.0) / 2.0) * math.log1p((x - mu) ** 2 / (degrees * scale2))
        )
        return max(math.exp(log_density), EPS)

    @staticmethod
    def _nig_update(mu: float, kappa: float, alpha: float, beta: float, x: float) -> Tuple[float, float, float, float]:
        new_kappa = kappa + 1.0
        new_mu = (kappa * mu + x) / new_kappa
        new_alpha = alpha + 0.5
        new_beta = beta + kappa * (x - mu) ** 2 / (2.0 * new_kappa)
        return new_mu, new_kappa, new_alpha, new_beta

    def _prior_predictive(self, state: int, x: float) -> float:
        return self._student_t_pdf(
            x,
            self.prior_mu[state],
            self.prior_kappa[state],
            self.prior_alpha[state],
            self.prior_beta[state],
        )

    def _reset_parameter_arrays(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        width = self.max_run_length + 1
        return (
            np.repeat(self.prior_mu[:, None], width, axis=1),
            np.repeat(self.prior_kappa[:, None], width, axis=1),
            np.repeat(self.prior_alpha[:, None], width, axis=1),
            np.repeat(self.prior_beta[:, None], width, axis=1),
        )

    def update(self, observation: float) -> RegimeEngineState:
        observation = float(np.clip(observation, -12.0, 12.0))
        new_joint = np.zeros_like(self.joint)
        new_mu, new_kappa, new_alpha, new_beta = self._reset_parameter_arrays()

        if not self.initialized:
            for state in range(self.n_states):
                new_joint[state, 0] = self.state_prior[state] * self._prior_predictive(state, observation)
                updated = self._nig_update(
                    self.prior_mu[state], self.prior_kappa[state],
                    self.prior_alpha[state], self.prior_beta[state], observation,
                )
                new_mu[state, 0], new_kappa[state, 0], new_alpha[state, 0], new_beta[state, 0] = updated
            self.initialized = True
        else:
            switch_mass = np.zeros(self.n_states, dtype=float)
            for source_state in range(self.n_states):
                occupied = np.flatnonzero(self.joint[source_state] > 0)
                for run in occupied:
                    probability = self.joint[source_state, run]
                    predictive = self._student_t_pdf(
                        observation,
                        self.mu[source_state, run], self.kappa[source_state, run],
                        self.alpha[source_state, run], self.beta[source_state, run],
                    )
                    hazard = self._hazard(source_state, int(run))
                    if run < self.max_run_length:
                        new_joint[source_state, run + 1] += probability * (1.0 - hazard) * predictive
                        updated = self._nig_update(
                            self.mu[source_state, run], self.kappa[source_state, run],
                            self.alpha[source_state, run], self.beta[source_state, run], observation,
                        )
                        new_mu[source_state, run + 1], new_kappa[source_state, run + 1], new_alpha[source_state, run + 1], new_beta[source_state, run + 1] = updated
                    switch_mass += probability * hazard * self.transition[source_state]

            for target_state in range(self.n_states):
                new_joint[target_state, 0] = switch_mass[target_state] * self._prior_predictive(target_state, observation)
                updated = self._nig_update(
                    self.prior_mu[target_state], self.prior_kappa[target_state],
                    self.prior_alpha[target_state], self.prior_beta[target_state], observation,
                )
                new_mu[target_state, 0], new_kappa[target_state, 0], new_alpha[target_state, 0], new_beta[target_state, 0] = updated

        evidence = float(new_joint.sum())
        if not np.isfinite(evidence) or evidence <= EPS:
            raise FloatingPointError("Regime engine posterior normalization failed")
        new_joint /= evidence
        self.joint = new_joint
        self.mu, self.kappa, self.alpha, self.beta = new_mu, new_kappa, new_alpha, new_beta

        state_probability = new_joint.sum(axis=1)
        change_by_state = new_joint[:, 0]
        p_change = float(change_by_state.sum())
        conditional_new = change_by_state / max(p_change, EPS)
        runs = np.arange(self.max_run_length + 1, dtype=float)
        expected_run = float(np.sum(new_joint * runs[None, :]))
        entropy = float(-np.sum(new_joint * np.log(new_joint + EPS)))

        remaining = 0.0
        for state in range(self.n_states):
            mean_duration = self.duration_medians[state] * math.exp(0.5 * self.duration_sigma[state] ** 2)
            remaining += float(np.sum(new_joint[state] * np.maximum(mean_duration - (runs + 1.0), 0.0)))

        return RegimeEngineState(
            p_change=p_change,
            expected_run_length=expected_run,
            hsmm_remaining_duration=remaining,
            entropy=entropy,
            regime_probabilities=dict(zip(self.states, state_probability)),
            new_regime_probabilities=dict(zip(self.states, conditional_new)),
            most_likely_regime=self.states[int(np.argmax(state_probability))],
        )


# ---------------------------------------------------------------------------
# 전문가 학습용 regime label (실시간 regime posterior에는 사용하지 않음)
# ---------------------------------------------------------------------------


def make_regime_labels(features: pd.DataFrame) -> pd.Series:
    """학습 전용 미래 라벨. 실시간 추론에 절대 입력하지 않는다."""
    scale = features["vol_20"].clip(lower=0.003)
    threshold = 0.35 * scale
    target = features["target"]
    label = pd.Series("sideways", index=features.index, dtype="object")
    label[target > threshold] = "bull"
    label[target < -threshold] = "bear"
    return label


# ---------------------------------------------------------------------------
# Expert models
# ---------------------------------------------------------------------------


class TabularExpert:
    """XGBoost/LightGBM이 있으면 사용하고, 없으면 sklearn fallback 사용."""

    def __init__(self, kind: str, seed: int):
        self.kind = kind
        self.seed = seed
        self.model = self._make_model()
        self.residual_variance = 1e-4
        self.fitted = False

    def _make_model(self):
        if self.kind == "xgboost":
            try:
                from xgboost import XGBRegressor
                return XGBRegressor(
                    n_estimators=250, max_depth=3, learning_rate=0.04,
                    subsample=0.8, colsample_bytree=0.8,
                    objective="reg:squarederror", random_state=self.seed, n_jobs=1,
                )
            except ImportError:
                return GradientBoostingRegressor(
                    n_estimators=180, max_depth=3, learning_rate=0.04,
                    loss="huber", random_state=self.seed,
                )
        if self.kind == "lightgbm":
            try:
                from lightgbm import LGBMRegressor
                return LGBMRegressor(
                    n_estimators=250, max_depth=4, learning_rate=0.04,
                    subsample=0.8, colsample_bytree=0.8,
                    random_state=self.seed, verbosity=-1, n_jobs=1,
                )
            except ImportError:
                return HistGradientBoostingRegressor(
                    max_iter=180, max_depth=4, learning_rate=0.04,
                    l2_regularization=1.0, random_state=self.seed,
                )
        raise ValueError(f"지원하지 않는 tabular expert: {self.kind}")

    def fit(self, x: pd.DataFrame, y: pd.Series) -> None:
        self.model.fit(x, y)
        residual = y.to_numpy() - self.model.predict(x)
        self.residual_variance = float(max(np.var(residual), 1e-6))
        self.fitted = True

    def predict(self, row: pd.DataFrame) -> PredictiveDistribution:
        if not self.fitted:
            return PredictiveDistribution(0.0, 1.0, 0.5, False, "not_fitted")
        mean = float(self.model.predict(row)[0])
        sd = math.sqrt(self.residual_variance)
        p_up = normal_cdf(mean / max(sd, EPS))
        return PredictiveDistribution(mean, self.residual_variance, p_up)


class LSTMExpert:
    """가벼운 sequence expert.

    TensorFlow가 설치된 환경에서는 작은 LSTM을 사용한다. 그렇지 않으면 lag
    sequence를 펼친 Ridge 회귀를 사용하므로 전체 예제가 항상 실행 가능하다.
    """

    def __init__(self, lookback: int = 20, seed: int = 42):
        self.lookback = lookback
        self.seed = seed
        self.backend = "ridge_sequence_fallback"
        self.model = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=5.0))])
        self.keras = None
        try:
            import tensorflow as tf

            tf.keras.utils.set_random_seed(seed)
            self.keras = tf
            self.backend = "tensorflow_lstm"
            self.model = None
        except ImportError:
            pass
        self.residual_variance = 1e-4
        self.fitted = False

    def _sequences(self, values: np.ndarray, targets: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        xs, ys = [], []
        for i in range(self.lookback, len(values)):
            xs.append(values[i - self.lookback : i].reshape(-1))
            ys.append(targets[i])
        return np.asarray(xs), np.asarray(ys)

    def fit(self, x: pd.DataFrame, y: pd.Series) -> None:
        xs, ys = self._sequences(x.to_numpy(dtype=float), y.to_numpy(dtype=float))
        if len(xs) < 50:
            self.fitted = False
            return
        if self.keras is not None:
            tf = self.keras
            xs_3d = xs.reshape(len(xs), self.lookback, x.shape[1])
            model = tf.keras.Sequential(
                [
                    tf.keras.layers.Input((self.lookback, x.shape[1])),
                    tf.keras.layers.LSTM(32, dropout=0.15),
                    tf.keras.layers.Dense(1),
                ]
            )
            model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss=tf.keras.losses.Huber())
            model.fit(xs_3d, ys, epochs=8, batch_size=32, validation_split=0.15, verbose=0)
            self.model = model
            fitted = model.predict(xs_3d, verbose=0).reshape(-1)
        else:
            self.model.fit(xs, ys)
            fitted = self.model.predict(xs)
        residual = ys - fitted
        self.residual_variance = float(max(np.var(residual), 1e-6))
        self.fitted = True

    def predict(self, history: pd.DataFrame) -> PredictiveDistribution:
        if not self.fitted or len(history) < self.lookback:
            return PredictiveDistribution(0.0, 1.0, 0.5, False, "insufficient_sequence")
        sequence = history.iloc[-self.lookback :].to_numpy(dtype=float).reshape(1, -1)
        if self.keras is not None:
            sequence = sequence.reshape(1, self.lookback, history.shape[1])
            mean = float(self.model.predict(sequence, verbose=0).reshape(-1)[0])
        else:
            mean = float(self.model.predict(sequence)[0])
        sd = math.sqrt(self.residual_variance)
        return PredictiveDistribution(mean, self.residual_variance, normal_cdf(mean / sd))


class KalmanMeanReversionExpert:
    def __init__(self, process_var: float = 1e-5, observation_var: float = 2e-4):
        self.q, self.r = process_var, observation_var
        self.mean: Optional[float] = None
        self.state_var = 1.0

    def update_and_predict(self, log_price: float) -> PredictiveDistribution:
        if self.mean is None:
            self.mean = log_price
            return PredictiveDistribution(0.0, self.r, 0.5, False, "warmup")
        predicted_var = self.state_var + self.q
        gain = predicted_var / (predicted_var + self.r)
        innovation = log_price - self.mean
        self.mean += gain * innovation
        self.state_var = (1 - gain) * predicted_var
        expected_reversion = -0.25 * (log_price - self.mean)
        variance = max(self.state_var + self.r, 1e-6)
        return PredictiveDistribution(
            expected_reversion, variance, normal_cdf(expected_reversion / math.sqrt(variance))
        )


class OUExpert:
    def __init__(self, window: int = 120, min_half_life: float = 2, max_half_life: float = 40):
        self.window = window
        self.min_half_life = min_half_life
        self.max_half_life = max_half_life

    def predict(self, log_prices: pd.Series) -> PredictiveDistribution:
        x = log_prices.dropna().iloc[-self.window :].to_numpy(dtype=float)
        if len(x) < 60:
            return PredictiveDistribution(0.0, 1.0, 0.5, False, "ou_warmup")
        lag, nxt = x[:-1], x[1:]
        design = np.column_stack([np.ones(len(lag)), lag])
        intercept, phi = np.linalg.lstsq(design, nxt, rcond=None)[0]
        if not 0.0 < phi < 1.0:
            return PredictiveDistribution(0.0, 1.0, 0.5, False, "non_stationary")
        half_life = -math.log(2.0) / math.log(phi)
        if not self.min_half_life <= half_life <= self.max_half_life:
            return PredictiveDistribution(0.0, 1.0, 0.5, False, "half_life_out_of_range")
        theta = intercept / (1.0 - phi)
        mean = float((1.0 - phi) * (theta - x[-1]))
        residual = nxt - (intercept + phi * lag)
        variance = float(max(np.var(residual), 1e-6))
        return PredictiveDistribution(mean, variance, normal_cdf(mean / math.sqrt(variance)))


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Bayesian Model Averaging
# ---------------------------------------------------------------------------


EXPERT_REGIME = {
    "bull_lstm": "bull",
    "bull_xgb": "bull",
    "bear_lgbm": "bear",
    "side_kalman": "sideways",
    "side_ou": "sideways",
}


class BayesianModelAverager:
    def __init__(self, forgetting: float, floor: float, cap: float):
        self.forgetting = forgetting
        self.floor = floor
        self.cap = cap
        self.log_reliability = {name: 0.0 for name in EXPERT_REGIME}
        self.previous_forecasts: Dict[str, PredictiveDistribution] = {}

    def weights(
        self,
        regime_probabilities: Mapping[str, float],
        forecasts: Mapping[str, PredictiveDistribution],
        p_change: float,
    ) -> Dict[str, float]:
        eligible = {k: v for k, v in forecasts.items() if v.valid and np.isfinite(v.mean + v.variance)}
        if not eligible:
            return {}
        logw = {}
        shrink = max(0.25, 1.0 - p_change)
        for name in eligible:
            regime = EXPERT_REGIME[name]
            logw[name] = math.log(max(regime_probabilities[regime], EPS)) + shrink * self.log_reliability[name]
        pivot = max(logw.values())
        raw = {k: math.exp(v - pivot) for k, v in logw.items()}
        total = sum(raw.values())
        weights = {k: v / total for k, v in raw.items()}
        weights = {k: min(self.cap, max(self.floor, v)) for k, v in weights.items()}
        norm = sum(weights.values())
        weights = {k: v / norm for k, v in weights.items()}
        self.previous_forecasts = dict(eligible)
        return weights

    def update(self, realized_return: float) -> None:
        for name, pred in self.previous_forecasts.items():
            var = max(pred.variance, 1e-8)
            log_likelihood = -0.5 * (math.log(2 * math.pi * var) + (realized_return - pred.mean) ** 2 / var)
            bounded = float(np.clip(log_likelihood, -20.0, 10.0))
            self.log_reliability[name] = self.forgetting * self.log_reliability[name] + bounded
        if self.log_reliability:
            center = max(self.log_reliability.values())
            self.log_reliability = {k: v - center for k, v in self.log_reliability.items()}

    @staticmethod
    def combine(
        forecasts: Mapping[str, PredictiveDistribution], weights: Mapping[str, float]
    ) -> PredictiveDistribution:
        if not weights:
            return PredictiveDistribution(0.0, 1.0, 0.5, False, "no_eligible_expert")
        mean = sum(weights[k] * forecasts[k].mean for k in weights)
        second = sum(
            weights[k] * (forecasts[k].variance + forecasts[k].mean ** 2) for k in weights
        )
        variance = max(second - mean**2, 1e-8)
        p_up = sum(weights[k] * forecasts[k].p_up for k in weights)
        return PredictiveDistribution(mean, variance, p_up)


# ---------------------------------------------------------------------------
# Kelly, risk gate, paper execution
# ---------------------------------------------------------------------------


class CostModel:
    def __init__(self, config: Config):
        self.one_way_rate = (config.commission_bps + config.spread_bps + config.slippage_bps) / 10_000

    def expected_return_cost(self, turnover: float) -> float:
        return self.one_way_rate * abs(turnover)


def fractional_kelly(
    predictive: PredictiveDistribution,
    regime_probabilities: Mapping[str, float],
    current_weight: float,
    cost_model: CostModel,
    config: Config,
) -> Tuple[float, float]:
    entropy = -sum(p * math.log(p + EPS) for p in regime_probabilities.values()) / math.log(3)
    uncertainty_multiplier = max(0.0, 1.0 - entropy)
    approximate_turnover = max(0.05, abs(predictive.mean / max(predictive.variance, EPS) - current_weight))
    mu_net = predictive.mean - math.copysign(
        cost_model.expected_return_cost(approximate_turnover), predictive.mean
    )
    buffer = config.uncertainty_z * math.sqrt(max(predictive.variance, config.variance_floor))
    if abs(mu_net) <= buffer:
        return 0.0, mu_net
    raw = mu_net / max(predictive.variance, config.variance_floor)
    target = config.kelly_fraction * raw * uncertainty_multiplier
    return float(np.clip(target, -config.max_short_weight, config.max_long_weight)), mu_net


class RiskGate:
    def __init__(self, config: Config):
        self.config = config

    def approve(
        self,
        raw_target: float,
        current_weight: float,
        realized_vol_daily: float,
        p_change: float,
        portfolio: PortfolioState,
    ) -> RiskDecision:
        if portfolio.kill_switch:
            return RiskDecision(0.0, False, "kill_switch")
        drawdown = 1.0 - portfolio.equity / max(portfolio.peak_equity, EPS)
        daily_return = portfolio.equity / max(portfolio.last_equity, EPS) - 1.0
        if drawdown >= self.config.max_drawdown:
            portfolio.kill_switch = True
            return RiskDecision(0.0, False, "max_drawdown")
        if daily_return <= -self.config.max_daily_loss:
            return RiskDecision(0.0, False, "daily_loss_limit")

        annualized_vol = max(realized_vol_daily * math.sqrt(252), 1e-4)
        vol_scale = min(1.0, self.config.annual_vol_target / annualized_vol)
        cp_haircut = 0.50 if p_change >= self.config.cp_alert else 1.0
        target = raw_target * vol_scale * cp_haircut
        delta = float(np.clip(target - current_weight, -self.config.max_turnover_per_bar, self.config.max_turnover_per_bar))
        target = current_weight + delta
        target = float(np.clip(target, -self.config.max_short_weight, self.config.max_long_weight))
        if abs(target - current_weight) < self.config.no_trade_band:
            return RiskDecision(current_weight, True, "no_trade_band")
        return RiskDecision(target, True, "approved")


class PaperBroker:
    """다음 bar Open에서 목표 비중으로 재조정하는 단순 페이퍼 브로커."""

    def __init__(self, initial_cash: float, cost_model: CostModel):
        self.state = PortfolioState(cash=initial_cash, equity=initial_cash, peak_equity=initial_cash, last_equity=initial_cash)
        self.cost_model = cost_model

    def mark_to_market(self, close: float) -> None:
        self.state.last_equity = self.state.equity
        self.state.equity = self.state.cash + self.state.units * close
        self.state.peak_equity = max(self.state.peak_equity, self.state.equity)

    def current_weight(self, price: float) -> float:
        return self.state.units * price / max(self.state.equity, EPS)

    def rebalance_at_open(self, target_weight: float, open_price: float) -> float:
        equity_before = self.state.cash + self.state.units * open_price
        desired_units = target_weight * equity_before / open_price
        traded_units = desired_units - self.state.units
        traded_notional = abs(traded_units * open_price)
        cost = traded_notional * self.cost_model.one_way_rate
        self.state.cash -= traded_units * open_price + cost
        self.state.units = desired_units
        self.state.equity = self.state.cash + self.state.units * open_price
        return cost


# ---------------------------------------------------------------------------
# 통합 전략과 walk-forward 백테스트
# ---------------------------------------------------------------------------


class RegimeAdaptiveStrategy:
    def __init__(self, config: Config):
        self.config = config
        self.lstm = LSTMExpert(lookback=20, seed=config.seed)
        self.xgb = TabularExpert("xgboost", config.seed)
        self.lgbm = TabularExpert("lightgbm", config.seed)
        self.kalman = KalmanMeanReversionExpert()
        self.ou = OUExpert()
        self.bma = BayesianModelAverager(config.bma_forgetting, config.bma_weight_floor, config.bma_weight_cap)
        self.costs = CostModel(config)
        self.risk = RiskGate(config)
        self.last_fit_index = -10**9

    def fit(self, train: pd.DataFrame, current_index: int) -> None:
        clean = train.dropna(subset=FEATURE_COLUMNS + ["target"])
        if len(clean) < self.config.min_train_rows:
            return
        labels = make_regime_labels(clean)

        bull = clean.loc[labels == "bull"]
        bear = clean.loc[labels == "bear"]
        if len(bull) >= 80:
            self.xgb.fit(bull[FEATURE_COLUMNS], bull["target"])
        if len(bear) >= 80:
            self.lgbm.fit(bear[FEATURE_COLUMNS], bear["target"])
        # LSTM fallback은 연속 시퀀스 보존을 위해 전체 데이터로 학습한다.
        self.lstm.fit(clean[FEATURE_COLUMNS], clean["target"])
        self.last_fit_index = current_index

    def forecasts(self, history: pd.DataFrame) -> Dict[str, PredictiveDistribution]:
        row = history.iloc[[-1]][FEATURE_COLUMNS]
        log_prices = np.log(history["Close"])
        return {
            "bull_lstm": self.lstm.predict(history[FEATURE_COLUMNS].dropna()),
            "bull_xgb": self.xgb.predict(row),
            "bear_lgbm": self.lgbm.predict(row),
            "side_kalman": self.kalman.update_and_predict(float(log_prices.iloc[-1])),
            "side_ou": self.ou.predict(log_prices),
        }


def attach_regime_engine_features(features: pd.DataFrame, config: Config) -> pd.DataFrame:
    """Robust BOCPDMS-HSMM posterior를 인과적으로 피처 프레임에 부착한다."""
    engine = RobustBOCPDMSHSMM(
        max_run_length=config.bocpd_max_run_length,
        duration_medians={
            "bull": config.hsmm_bull_median_duration,
            "bear": config.hsmm_bear_median_duration,
            "sideways": config.hsmm_sideways_median_duration,
        },
        duration_sigma=config.hsmm_duration_sigma,
    )
    values = features["ret_1"].fillna(0.0)
    expanding_mean = values.expanding(min_periods=20).mean().shift(1).fillna(0.0)
    expanding_std = values.expanding(min_periods=20).std(ddof=0).shift(1).fillna(0.01).clip(lower=1e-4)
    records = []
    for value, mean, std in zip(values, expanding_mean, expanding_std):
        posterior = engine.update(float(np.clip((value - mean) / std, -12, 12)))
        records.append(
            {
                "p_change": posterior.p_change,
                "run_length": posterior.expected_run_length,
                "hsmm_remaining_duration": posterior.hsmm_remaining_duration,
                "regime_entropy": posterior.entropy,
                "engine_regime": posterior.most_likely_regime,
                **{f"p_{name}_engine": probability for name, probability in posterior.regime_probabilities.items()},
                **{f"p_new_{name}": probability for name, probability in posterior.new_regime_probabilities.items()},
            }
        )
    state = pd.DataFrame(records, index=features.index)
    return features.join(state)


def run_backtest(ohlcv: pd.DataFrame, config: Config) -> BacktestResult:
    prices = validate_ohlcv(ohlcv)
    features = attach_regime_engine_features(build_features(prices, config.horizon), config).join(
        prices[["Open", "High", "Low", "Close", "Volume"]]
    )
    strategy = RegimeAdaptiveStrategy(config)
    broker = PaperBroker(config.initial_cash, strategy.costs)
    rows = []

    start = max(config.min_train_rows, 80)
    pending_target = 0.0
    for i in range(start, len(features) - config.horizon):
        date = features.index[i]
        row = features.iloc[i]
        if row[FEATURE_COLUMNS].isna().any():
            continue

        # 전일 종가에 결정한 목표를 금일 시가에 집행한다.
        trading_cost = broker.rebalance_at_open(pending_target, float(row["Open"]))
        broker.mark_to_market(float(row["Close"]))
        current_weight = broker.current_weight(float(row["Close"]))

        if i - strategy.last_fit_index >= config.retrain_every:
            # 현재 행의 target은 미래를 포함하므로 학습 데이터에서 제외한다.
            strategy.fit(features.iloc[: i - config.horizon], i)

        # 직전 bar에서 만든 예측은 현재 종가에서 처음 관측 가능하다.
        # 새 가중치를 만들기 전에 갱신하여 미래 수익률 누수를 막는다.
        previous_realized = float(features.iloc[i - 1]["target"])
        if np.isfinite(previous_realized):
            strategy.bma.update(previous_realized)

        regime_p = {name: float(row[f"p_{name}_engine"]) for name in REGIMES}
        history = features.iloc[: i + 1]
        forecasts = strategy.forecasts(history)
        weights = strategy.bma.weights(regime_p, forecasts, float(row["p_change"]))
        predictive = strategy.bma.combine(forecasts, weights)

        if predictive.valid:
            raw_target, mu_net = fractional_kelly(
                predictive, regime_p, current_weight, strategy.costs, config
            )
        else:
            raw_target, mu_net = 0.0, 0.0
        realized_vol = float(max(row["vol_20"], 1e-4))
        decision = strategy.risk.approve(
            raw_target, current_weight, realized_vol, float(row["p_change"]), broker.state
        )
        pending_target = decision.target_weight

        rows.append(
            {
                "date": date,
                "equity": broker.state.equity,
                "current_weight": current_weight,
                "target_weight": pending_target,
                "p_change": row["p_change"],
                "engine_regime": row["engine_regime"],
                "expected_run_length": row["run_length"],
                "hsmm_remaining_duration": row["hsmm_remaining_duration"],
                "regime_entropy": row["regime_entropy"],
                **{f"p_new_{name}": row[f"p_new_{name}"] for name in REGIMES},
                **{f"p_{k}": v for k, v in regime_p.items()},
                "forecast_mean": predictive.mean,
                "forecast_variance": predictive.variance,
                "mu_net": mu_net,
                "trading_cost": trading_cost,
                "risk_reason": decision.reason,
                "bma_weights": json.dumps(weights, ensure_ascii=False),
            }
        )

    decisions = pd.DataFrame(rows).set_index("date")
    equity = decisions["equity"]
    returns = equity.pct_change().fillna(0.0)
    metrics = performance_metrics(equity, returns, decisions["trading_cost"])
    return BacktestResult(equity, returns, decisions, metrics)


def performance_metrics(equity: pd.Series, returns: pd.Series, costs: pd.Series) -> Dict[str, float]:
    if len(equity) < 2:
        return {}
    years = len(equity) / 252.0
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / max(years, EPS)) - 1
    annual_vol = returns.std(ddof=0) * math.sqrt(252)
    sharpe = returns.mean() / max(returns.std(ddof=0), EPS) * math.sqrt(252)
    drawdown = equity / equity.cummax() - 1.0
    return {
        "final_equity": float(equity.iloc[-1]),
        "cagr": float(cagr),
        "annual_volatility": float(annual_vol),
        "sharpe_zero_rf": float(sharpe),
        "max_drawdown": float(drawdown.min()),
        "total_trading_cost": float(costs.sum()),
        "bars": int(len(equity)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Robust BOCPDMS-HSMM 레짐 적응형 자동매매 참조 구현")
    parser.add_argument("--csv", type=Path, help="Date/Open/High/Low/Close/Volume CSV")
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--output", type=Path, help="의사결정 로그 CSV 저장 경로")
    parser.add_argument("--rows", type=int, default=1_500, help="합성 데이터 행 수")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = Config(initial_cash=args.initial_cash)
    data = pd.read_csv(args.csv) if args.csv else make_synthetic_ohlcv(args.rows, config.seed)
    data = validate_ohlcv(data)
    LOGGER.info("백테스트 시작: %s ~ %s, %d bars", data.index.min().date(), data.index.max().date(), len(data))
    result = run_backtest(data, config)
    print(json.dumps(result.metrics, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result.decisions.to_csv(args.output, encoding="utf-8-sig")
        LOGGER.info("의사결정 로그 저장: %s", args.output.resolve())


if __name__ == "__main__":
    main()
