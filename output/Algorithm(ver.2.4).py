"""
Algorithm(ver.2.4).py
===================
BOCPD + HMM (Markov Switching) + LightGBM -> regime experts -> BMA -> fractional Kelly
-> calibrated expert×regime BMA -> core/satellite -> durable execution.

주의
----
- 교육·연구용 예시이며 실거래용 완제품이 아닙니다.
- 기본 실행은 합성 일봉 데이터를 사용하고 주문은 PaperBroker에만 기록합니다.
- 실제 운용 전 point-in-time 데이터, 거래비용, 체결, 원장 대사, 규제 및
  장애 대응을 별도로 구현하고 검증해야 합니다.

실행 예시
---------
    python "Algorithm(ver.2.4).py"
    python "Algorithm(ver.2.4).py" --csv prices.csv --state-file state.json

CSV 필수 열: Date, Open, High, Low, Close, Volume
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import (
        GradientBoostingRegressor,
        HistGradientBoostingClassifier,
        HistGradientBoostingRegressor,
    )
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
    bocpd_expected_run_length: int = 60
    hmm_self_transition: float = 0.94
    cp_alert: float = 0.35
    bma_forgetting: float = 0.985
    bma_weight_floor: float = 0.01
    bma_weight_cap: float = 0.70
    bma_change_decay: float = 0.25
    bma_change_threshold: float = 0.20
    residual_variance_window: int = 63
    residual_variance_min_obs: int = 20
    min_effective_train_rows: int = 100
    # ver.2.1: 시장 추종 코어와 Kelly 전술 위성을 분리한다.
    core_equity_weight: float = 0.70
    kelly_fraction: float = 0.25
    max_long_weight: float = 1.00
    max_short_weight: float = 0.00
    annual_vol_target: float = 0.15
    max_daily_loss: float = 0.025
    daily_loss_cooldown_bars: int = 1
    max_drawdown: float = 0.12
    kill_switch_cooldown_bars: int = 5
    kill_switch_reentry_total_bars: int = 10
    stop_cooldown_bars: int = 1
    stop_reentry_total_bars: int = 3
    daily_loss_reentry_total_bars: int = 4
    max_turnover_per_bar: float = 0.25
    no_trade_band: float = 0.02
    commission_bps: float = 1.0
    spread_bps: float = 2.0
    slippage_bps: float = 2.0
    uncertainty_z: float = 0.10
    entropy_multiplier_floor: float = 0.50
    momentum_120_bull_multiplier: float = 1.15
    momentum_120_bear_multiplier: float = 0.65
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
class BOCPDState:
    p_change: float
    expected_run_length: float
    entropy: float


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
    previous_close_equity: float = 0.0
    all_time_peak_equity: float = 0.0
    risk_cycle_peak_equity: float = 0.0
    risk_state: str = "NORMAL"
    risk_cooldown_remaining: int = 0
    reentry_bars_elapsed: int = 0
    reentry_duration_bars: int = 0
    reentry_source: str = ""
    risk_weight_cap: float = 1.0
    risk_release_count: int = 0
    kill_switch: bool = False
    kill_switch_bars_remaining: int = 0


@dataclass
class AlgorithmPositionRiskState:
    """별도 loss-cut 모듈과 공유하는 최소 포지션 상태."""

    entry_price: float = 0.0
    entry_timestamp: pd.Timestamp | None = None
    side: str = "FLAT"
    entry_regime: str = ""
    entry_expert: str = ""
    highest_price_since_entry: float = 0.0
    lowest_price_since_entry: float = float("inf")
    initial_stop: float | None = None
    active_stop: float | None = None
    initial_risk_r: float | None = None
    holding_bars: int = 0
    status: str = "INACTIVE"
    last_stop_reason: str = ""
    cooldown_until: pd.Timestamp | None = None
    last_observed_at: pd.Timestamp | None = None

    def open(self, price: float, units: float, timestamp: pd.Timestamp | None = None) -> None:
        self.entry_price = float(price)
        self.entry_timestamp = pd.Timestamp(timestamp) if timestamp is not None else None
        self.side = "LONG" if units > 0 else "SHORT"
        self.entry_regime = ""
        self.entry_expert = ""
        self.highest_price_since_entry = float(price)
        self.lowest_price_since_entry = float(price)
        self.initial_stop = None
        self.active_stop = None
        self.initial_risk_r = None
        self.holding_bars = 0
        self.status = "MONITORING"
        self.last_stop_reason = ""
        self.cooldown_until = None
        self.last_observed_at = self.entry_timestamp

    def observe_price(self, price: float, timestamp: pd.Timestamp | None = None) -> None:
        if self.side == "FLAT":
            return
        value = float(price)
        self.highest_price_since_entry = max(self.highest_price_since_entry, value)
        self.lowest_price_since_entry = min(self.lowest_price_since_entry, value)
        observed_at = pd.Timestamp(timestamp) if timestamp is not None else None
        if observed_at is None or self.last_observed_at is None or observed_at > self.last_observed_at:
            self.holding_bars += 1
        self.last_observed_at = observed_at


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    decisions: pd.DataFrame
    metrics: Dict[str, float]


class StateIntegrityError(RuntimeError):
    """체크포인트 손상·설정 불일치·시장 데이터 불일치."""


class ReconciliationError(RuntimeError):
    """체크포인트와 외부 broker/account snapshot 불일치."""


@dataclass(frozen=True)
class BrokerAccountSnapshot:
    cash: float
    units: float
    last_price: float
    as_of: pd.Timestamp
    open_orders: Tuple[str, ...] = ()

    @property
    def equity(self) -> float:
        return float(self.cash + self.units * self.last_price)

    @classmethod
    def from_json_file(cls, path: Path) -> "BrokerAccountSnapshot":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            cash=float(raw["cash"]), units=float(raw["units"]),
            last_price=float(raw["last_price"]),
            as_of=pd.Timestamp(raw["as_of"]),
            open_orders=tuple(str(v) for v in raw.get("open_orders", [])),
        )


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _canonical_json(payload: Mapping[str, object]) -> str:
    return json.dumps(_json_safe(dict(payload)), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class JsonStateStore:
    """Checksum 검증과 같은 디렉터리 atomic replace를 사용하는 상태 저장소."""

    schema_version = 1

    def __init__(self, path: Path):
        self.path = Path(path)

    def save(self, payload: Mapping[str, object]) -> None:
        body = {"schema_version": self.schema_version, **dict(payload)}
        canonical = _canonical_json(body)
        wrapper = {"payload": _json_safe(body), "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent,
            prefix=f".{self.path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            json.dump(wrapper, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        temp_path.replace(self.path)

    def load(self) -> Dict[str, object]:
        if not self.path.exists():
            raise FileNotFoundError(f"체크포인트가 없습니다: {self.path}")
        wrapper = json.loads(self.path.read_text(encoding="utf-8"))
        payload = wrapper.get("payload")
        if not isinstance(payload, dict):
            raise StateIntegrityError("체크포인트 payload 형식이 잘못되었습니다.")
        expected = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        if wrapper.get("sha256") != expected:
            raise StateIntegrityError("체크포인트 SHA-256 검증에 실패했습니다.")
        if payload.get("schema_version") != self.schema_version:
            raise StateIntegrityError("지원하지 않는 체크포인트 schema_version입니다.")
        return payload


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


def validate_config(config: Config) -> None:
    if not 0.0 <= config.core_equity_weight <= 1.0:
        raise ValueError("core_equity_weight는 0과 1 사이여야 합니다.")
    if not 0.0 <= config.entropy_multiplier_floor <= 1.0:
        raise ValueError("entropy_multiplier_floor는 0과 1 사이여야 합니다.")
    if config.max_short_weight != 0.0:
        raise ValueError("ver.2.1 MVP는 long-only이므로 max_short_weight는 0이어야 합니다.")
    if config.max_long_weight > 1.0 or config.max_long_weight < config.core_equity_weight:
        raise ValueError("max_long_weight는 core_equity_weight 이상 1 이하이어야 합니다.")
    periods = (
        config.kill_switch_cooldown_bars, config.daily_loss_cooldown_bars,
        config.stop_cooldown_bars, config.kill_switch_reentry_total_bars,
        config.stop_reentry_total_bars, config.daily_loss_reentry_total_bars,
    )
    if min(periods) < 1:
        raise ValueError("cooldown과 총 재진입 기간은 1 이상이어야 합니다.")
    if config.kill_switch_reentry_total_bars < config.kill_switch_cooldown_bars:
        raise ValueError("kill switch 총 재진입 기간은 cooldown 이상이어야 합니다.")
    if config.stop_reentry_total_bars < config.stop_cooldown_bars:
        raise ValueError("stop 총 재진입 기간은 cooldown 이상이어야 합니다.")
    if not 0.0 < config.bma_change_decay <= 1.0:
        raise ValueError("bma_change_decay는 0보다 크고 1 이하여야 합니다.")
    if not 0.0 <= config.bma_change_threshold <= 1.0:
        raise ValueError("bma_change_threshold는 0과 1 사이여야 합니다.")
    if not 2 <= config.residual_variance_min_obs <= config.residual_variance_window:
        raise ValueError("잔차 최소 관측 수는 2 이상이고 잔차 창 이하여야 합니다.")
    if config.min_effective_train_rows < 50:
        raise ValueError("min_effective_train_rows는 50 이상이어야 합니다.")
    if min(config.momentum_120_bull_multiplier, config.momentum_120_bear_multiplier) <= 0:
        raise ValueError("120일 모멘텀 배수는 0보다 커야 합니다.")


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
    for window in (5, 20, 60, 120):
        f[f"ret_{window}"] = log_price.diff(window)
        f[f"vol_{window}"] = log_ret.rolling(window).std(ddof=0)
        f[f"ma_gap_{window}"] = close / close.rolling(window).mean() - 1.0
    f["ema_slope"] = close.ewm(span=12, adjust=False).mean().pct_change(5)
    f["ma_slope_120"] = close.rolling(120).mean().pct_change(20)
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
    "ret_1", "ret_5", "ret_20", "ret_60", "ret_120", "vol_5", "vol_20", "vol_60", "vol_120",
    "ma_gap_5", "ma_gap_20", "ma_gap_60", "ma_gap_120", "ma_slope_120", "ema_slope", "atr_14",
    "downside_vol", "bollinger_z", "bollinger_width", "volume_z", "range_pct",
]


# ---------------------------------------------------------------------------
# BOCPD + LightGBM emission + HMM Markov switching
# ---------------------------------------------------------------------------


class StudentTBOCPD:
    """NIG conjugacy를 사용하는 Student-t posterior-predictive BOCPD."""

    def __init__(self, expected_run_length: int = 60, max_run_length: int = 180):
        self.hazard = 1.0 / expected_run_length
        self.max_run_length = max_run_length
        self.prior = (0.0, 1.0, 2.5, 1.5)  # mu, kappa, alpha, beta
        self.run_probs = np.array([1.0])
        self.mu = np.array([self.prior[0]])
        self.kappa = np.array([self.prior[1]])
        self.alpha = np.array([self.prior[2]])
        self.beta = np.array([self.prior[3]])

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
    def _update_nig(mu: float, kappa: float, alpha: float, beta: float, x: float) -> Tuple[float, float, float, float]:
        next_kappa = kappa + 1.0
        return (
            (kappa * mu + x) / next_kappa,
            next_kappa,
            alpha + 0.5,
            beta + kappa * (x - mu) ** 2 / (2.0 * next_kappa),
        )

    def update(self, observation: float) -> BOCPDState:
        x = float(np.clip(observation, -12.0, 12.0))
        likelihood = np.array(
            [self._student_t_pdf(x, *params) for params in zip(self.mu, self.kappa, self.alpha, self.beta)]
        )
        prior_likelihood = self._student_t_pdf(x, *self.prior)
        growth = self.run_probs * likelihood * (1.0 - self.hazard)
        change = prior_likelihood * self.hazard * float(self.run_probs.sum())
        new_probs = np.concatenate([[change], growth])[: self.max_run_length + 1]
        new_probs /= new_probs.sum() + EPS

        updated = [self._update_nig(*params, x) for params in zip(self.mu, self.kappa, self.alpha, self.beta)]
        prior_updated = self._update_nig(*self.prior, x)
        all_updated = [prior_updated] + updated
        width = len(new_probs)
        self.mu = np.array([p[0] for p in all_updated[:width]])
        self.kappa = np.array([p[1] for p in all_updated[:width]])
        self.alpha = np.array([p[2] for p in all_updated[:width]])
        self.beta = np.array([p[3] for p in all_updated[:width]])
        self.run_probs = new_probs

        runs = np.arange(width, dtype=float)
        return BOCPDState(
            p_change=float(new_probs[0]),
            expected_run_length=float(np.dot(runs, new_probs)),
            entropy=float(-np.sum(new_probs * np.log(new_probs + EPS))),
        )


REGIME_FEATURE_COLUMNS = [
    "ret_5", "ret_20", "ret_60", "ret_120", "vol_5", "vol_20", "vol_60", "vol_120",
    "ma_gap_120", "ma_slope_120", "downside_vol", "bollinger_z", "bollinger_width", "ema_slope",
    "atr_14", "volume_z", "p_change", "run_length", "bocpd_entropy",
]


class LightGBMEmissionModel:
    """LightGBM의 P(state|x)를 HMM emission evidence로 변환한다."""

    def __init__(self, seed: int):
        self.seed = seed
        self.model = self._make_model()
        self.class_prior = np.full(3, 1 / 3)
        self.fitted = False
        self.backend = type(self.model).__name__

    def _make_model(self):
        try:
            from lightgbm import LGBMClassifier

            return LGBMClassifier(
                objective="multiclass",
                num_class=3,
                n_estimators=300,
                learning_rate=0.035,
                max_depth=4,
                num_leaves=15,
                subsample=0.85,
                colsample_bytree=0.85,
                reg_lambda=2.0,
                random_state=self.seed,
                verbosity=-1,
                n_jobs=1,
            )
        except ImportError:
            LOGGER.warning("lightgbm 미설치: HistGradientBoostingClassifier fallback 사용")
            return HistGradientBoostingClassifier(
                max_iter=220,
                learning_rate=0.04,
                max_depth=4,
                l2_regularization=2.0,
                random_state=self.seed,
            )

    def fit(self, x: pd.DataFrame, labels: pd.Series) -> None:
        mapping = {"bull": 0, "bear": 1, "sideways": 2}
        y = labels.map(mapping).astype(int).to_numpy()
        if len(np.unique(y)) < 3:
            raise ValueError("LightGBM emission 학습에는 세 레짐 표본이 모두 필요합니다.")
        self.class_prior = np.bincount(y, minlength=3).astype(float)
        self.class_prior /= self.class_prior.sum()
        self.model.fit(x, y)
        self.fitted = True

    def evidence(self, row: pd.DataFrame) -> np.ndarray:
        if not self.fitted:
            return np.ones(3, dtype=float)
        predicted = self.model.predict_proba(row)[0]
        by_class = dict(zip(self.model.classes_, predicted))
        posterior = np.array([by_class.get(i, EPS) for i in range(3)], dtype=float)
        # Discriminative posterior를 학습 class prior로 나누면 HMM에서 사용할 수
        # 있는 상대 emission likelihood가 된다: p(x|s) ∝ p(s|x)/p_train(s).
        evidence = np.maximum(posterior, EPS) / np.maximum(self.class_prior, EPS)
        return evidence / evidence.sum()


class MarkovSwitchingRegimeEngine:
    """BOCPD 변화확률로 전이행렬을 조절하는 3-state HMM forward filter."""

    def __init__(self, seed: int, self_transition: float = 0.94):
        off = (1.0 - self_transition) / 2.0
        self.base_transition = np.array(
            [[self_transition, off, off], [off, self_transition, off], [off, off, self_transition]],
            dtype=float,
        )
        self.change_transition = np.array(
            [[0.00, 0.30, 0.70], [0.25, 0.00, 0.75], [0.55, 0.45, 0.00]],
            dtype=float,
        )
        self.posterior = np.array([0.30, 0.25, 0.45], dtype=float)
        self.last_predictive_prior = self.posterior.copy()
        self.emission = LightGBMEmissionModel(seed)

    def fit(self, frame: pd.DataFrame, labels: pd.Series) -> None:
        self.emission.fit(frame[REGIME_FEATURE_COLUMNS], labels)

    def predict_proba(self, row: pd.DataFrame, p_change: float) -> Dict[str, float]:
        cp = float(np.clip(p_change, 0.0, 1.0))
        transition = (1.0 - cp) * self.base_transition + cp * self.change_transition
        transition /= transition.sum(axis=1, keepdims=True)
        self.last_predictive_prior = self.posterior @ transition
        evidence = self.emission.evidence(row[REGIME_FEATURE_COLUMNS])
        filtered = self.last_predictive_prior * evidence
        self.posterior = filtered / (filtered.sum() + EPS)
        return dict(zip(REGIMES, self.posterior))


# ---------------------------------------------------------------------------
# 전문가 학습용 regime label (실시간 regime posterior에는 사용하지 않음)
# ---------------------------------------------------------------------------


def make_current_regime_labels(features: pd.DataFrame) -> pd.Series:
    """현재까지의 120/60일 추세와 변동성만 사용하는 현재 레짐 라벨."""
    scale_120 = features["vol_60"].clip(lower=0.003) * math.sqrt(120)
    scale_60 = features["vol_60"].clip(lower=0.003) * math.sqrt(60)
    score = (
        features["ret_120"] / scale_120
        + 0.50 * features["ret_60"] / scale_60
        + 0.50 * features["ma_gap_120"] / scale_120
        + 0.25 * features["ma_slope_120"] / features["vol_20"].clip(lower=0.003)
    )
    lower, upper = score.quantile([0.30, 0.70])
    label = pd.Series("sideways", index=features.index, dtype="object")
    label[(score >= upper) & (features["ma_gap_120"] > 0)] = "bull"
    label[(score <= lower) & (features["ma_gap_120"] < 0)] = "bear"
    # 작은 표본이나 단방향 장에서도 emission classifier의 3개 클래스가
    # 사라지지 않도록 가장 강한/약한 현재 추세 표본을 보강한다.
    if "bull" not in set(label):
        label.loc[score.nlargest(max(1, len(score) // 10)).index] = "bull"
    if "bear" not in set(label):
        label.loc[score.nsmallest(max(1, len(score) // 10)).index] = "bear"
    return label


def make_direction_labels(features: pd.DataFrame) -> pd.Series:
    """전문가 평가용 다음 날 방향 라벨. 현재 레짐 학습에는 사용하지 않는다."""
    threshold = 0.10 * features["vol_20"].clip(lower=0.003)
    label = pd.Series("flat", index=features.index, dtype="object")
    label[features["target"] > threshold] = "up"
    label[features["target"] < -threshold] = "down"
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
        split = max(1, int(len(x) * 0.80))
        if len(x) - split < 20:
            split = len(x) - 20
        train_x, valid_x = x.iloc[:split], x.iloc[split:]
        train_y, valid_y = y.iloc[:split], y.iloc[split:]
        self.model.fit(train_x, train_y)
        residual = valid_y.to_numpy() - self.model.predict(valid_x)
        self.residual_variance = float(max(np.var(residual), 1e-6))
        # 분산은 시간순 표본외 구간에서 측정하고, 최종 평균모델은 공개된 전체
        # 학습 데이터로 다시 적합한다.
        self.model.fit(x, y)
        self.fitted = True

    def predict(self, row: pd.DataFrame) -> PredictiveDistribution:
        if not self.fitted:
            return PredictiveDistribution(0.0, 1.0, 0.5, False, "not_fitted")
        mean = float(self.model.predict(row)[0])
        sd = math.sqrt(self.residual_variance)
        p_up = normal_cdf(mean / max(sd, EPS))
        return PredictiveDistribution(mean, self.residual_variance, p_up)


class LSTMExpert:
    """시간 순서를 보존하는 표준화 LSTM expert (Ridge fallback 포함)."""

    def __init__(self, lookback: int = 20, seed: int = 42):
        self.lookback = lookback
        self.seed = seed
        self.backend = "ridge_sequence_fallback"
        self.model = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=5.0))])
        self.keras = None
        self.feature_scaler = StandardScaler()
        self.feature_columns: list[str] = []
        self.target_mean = 0.0
        self.target_scale = 1.0
        self.validation_loss = float("nan")
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
            xs.append(values[i - self.lookback : i])
            ys.append(targets[i])
        return np.asarray(xs), np.asarray(ys)

    def fit(self, x: pd.DataFrame, y: pd.Series) -> None:
        self.feature_columns = list(x.columns)
        xs, ys = self._sequences(x.to_numpy(dtype=np.float32), y.to_numpy(dtype=np.float32))
        if len(xs) < 50:
            self.fitted = False
            return
        if self.keras is not None:
            tf = self.keras
            split = max(1, int(len(xs) * 0.85))
            if len(xs) - split < 10:
                split = len(xs) - 10
            train_x, valid_x = xs[:split], xs[split:]
            train_y, valid_y = ys[:split], ys[split:]
            self.feature_scaler.fit(train_x.reshape(-1, x.shape[1]))
            transform = lambda z: self.feature_scaler.transform(z.reshape(-1, x.shape[1])).reshape(z.shape).astype(np.float32)
            train_x, valid_x = transform(train_x), transform(valid_x)
            self.target_mean = float(np.mean(train_y))
            self.target_scale = float(max(np.std(train_y), 1e-6))
            train_y_scaled = ((train_y - self.target_mean) / self.target_scale).astype(np.float32)
            valid_y_scaled = ((valid_y - self.target_mean) / self.target_scale).astype(np.float32)
            tf.keras.backend.clear_session()
            tf.keras.utils.set_random_seed(self.seed)
            model = tf.keras.Sequential(
                [
                    tf.keras.layers.Input((self.lookback, x.shape[1])),
                    tf.keras.layers.LSTM(32, dropout=0.15),
                    tf.keras.layers.Dense(16, activation="relu"),
                    tf.keras.layers.Dense(1),
                ]
            )
            model.compile(optimizer=tf.keras.optimizers.Adam(1e-3, clipnorm=1.0), loss=tf.keras.losses.Huber())
            history = model.fit(
                train_x, train_y_scaled, validation_data=(valid_x, valid_y_scaled),
                epochs=40, batch_size=32, shuffle=False, verbose=0,
                callbacks=[tf.keras.callbacks.EarlyStopping(
                    monitor="val_loss", patience=6, min_delta=1e-5, restore_best_weights=True,
                )],
            )
            self.model = model
            fitted = model.predict(valid_x, verbose=0).reshape(-1) * self.target_scale + self.target_mean
            residual = valid_y - fitted
            self.validation_loss = float(min(history.history["val_loss"]))
        else:
            flat = xs.reshape(len(xs), -1)
            self.model.fit(flat, ys)
            fitted = self.model.predict(flat)
            residual = ys - fitted
        self.residual_variance = float(max(np.var(residual), 1e-6))
        self.fitted = True

    def predict(self, history: pd.DataFrame) -> PredictiveDistribution:
        if not self.fitted or len(history) < self.lookback:
            return PredictiveDistribution(0.0, 1.0, 0.5, False, "insufficient_sequence")
        if list(history.columns) != self.feature_columns:
            history = history.reindex(columns=self.feature_columns)
        sequence = history.iloc[-self.lookback :].to_numpy(dtype=np.float32)
        if not np.isfinite(sequence).all():
            return PredictiveDistribution(0.0, 1.0, 0.5, False, "non_finite_sequence")
        if self.keras is not None:
            sequence = self.feature_scaler.transform(sequence).reshape(1, self.lookback, len(self.feature_columns))
            scaled_mean = float(self.model.predict(sequence, verbose=0).reshape(-1)[0])
            mean = scaled_mean * self.target_scale + self.target_mean
        else:
            mean = float(self.model.predict(sequence.reshape(1, -1))[0])
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
    "cash_no_trade": "any",
}


class BayesianModelAverager:
    def __init__(
        self, forgetting: float, floor: float, cap: float,
        change_decay: float, change_threshold: float,
        residual_window: int, residual_min_obs: int,
    ):
        self.forgetting = forgetting
        self.floor = floor
        self.cap = cap
        self.change_decay = change_decay
        self.change_threshold = change_threshold
        self.residual_window = residual_window
        self.residual_min_obs = residual_min_obs
        self.log_reliability = {
            name: {regime: 0.0 for regime in REGIMES} for name in EXPERT_REGIME
        }
        self.rolling_residuals: Dict[str, list[float]] = {name: [] for name in EXPERT_REGIME}
        self.previous_forecasts: Dict[str, PredictiveDistribution] = {}
        self.previous_regime_probabilities: Dict[str, float] = {r: 1 / 3 for r in REGIMES}

    def calibrate(
        self, forecasts: Mapping[str, PredictiveDistribution]
    ) -> Dict[str, PredictiveDistribution]:
        calibrated = {}
        for name, pred in forecasts.items():
            residuals = self.rolling_residuals.get(name, [])
            variance = pred.variance
            if len(residuals) >= self.residual_min_obs:
                sample = np.asarray(residuals[-self.residual_window:], dtype=float)
                lo, hi = np.quantile(sample, [0.05, 0.95])
                variance = float(max(np.var(np.clip(sample, lo, hi), ddof=1), 1e-6))
            sd = math.sqrt(max(variance, 1e-8))
            calibrated[name] = PredictiveDistribution(
                pred.mean, variance, normal_cdf(pred.mean / sd), pred.valid, pred.reason
            )
        return calibrated

    def weights(
        self,
        regime_probabilities: Mapping[str, float],
        forecasts: Mapping[str, PredictiveDistribution],
        p_change: float,
    ) -> Dict[str, float]:
        eligible = {k: v for k, v in forecasts.items() if v.valid and np.isfinite(v.mean + v.variance)}
        if not eligible:
            return {}
        if p_change >= self.change_threshold:
            self.log_reliability = {
                name: {regime: value * self.change_decay for regime, value in by_regime.items()}
                for name, by_regime in self.log_reliability.items()
            }
        logw = {}
        shrink = max(0.25, 1.0 - p_change)
        entropy = -sum(p * math.log(p + EPS) for p in regime_probabilities.values()) / math.log(3)
        for name in eligible:
            regime = EXPERT_REGIME[name]
            support = (
                0.10 + 0.60 * entropy if regime == "any"
                else regime_probabilities[regime]
            )
            reliability = sum(
                regime_probabilities[r] * self.log_reliability[name][r] for r in REGIMES
            )
            logw[name] = math.log(max(support, EPS)) + shrink * reliability
        pivot = max(logw.values())
        raw = {k: math.exp(v - pivot) for k, v in logw.items()}
        total = sum(raw.values())
        weights = {k: v / total for k, v in raw.items()}
        weights = {k: min(self.cap, max(self.floor, v)) for k, v in weights.items()}
        norm = sum(weights.values())
        weights = {k: v / norm for k, v in weights.items()}
        self.previous_forecasts = dict(eligible)
        self.previous_regime_probabilities = dict(regime_probabilities)
        return weights

    def update(self, realized_return: float) -> None:
        for name, pred in self.previous_forecasts.items():
            residual = float(realized_return - pred.mean)
            history = self.rolling_residuals.setdefault(name, [])
            history.append(residual)
            if len(history) > self.residual_window:
                del history[:-self.residual_window]
            var = max(pred.variance, 1e-8)
            log_likelihood = -0.5 * (math.log(2 * math.pi * var) + residual**2 / var)
            bounded = float(np.clip(log_likelihood, -20.0, 10.0))
            for regime in REGIMES:
                probability = self.previous_regime_probabilities.get(regime, 1 / 3)
                old = self.log_reliability[name][regime]
                self.log_reliability[name][regime] = self.forgetting * old + probability * bounded
        for regime in REGIMES:
            center = max(values[regime] for values in self.log_reliability.values())
            for name in self.log_reliability:
                self.log_reliability[name][regime] -= center

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
    # 레짐 불확실성이 높더라도 전술 슬리브의 절반은 유지한다. 시장 코어에는
    # 이 감쇄를 적용하지 않는다.
    uncertainty_multiplier = config.entropy_multiplier_floor + (
        1.0 - config.entropy_multiplier_floor
    ) * max(0.0, 1.0 - entropy)
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


def apply_120d_momentum(
    tactical_target: float, row: pd.Series, config: Config
) -> Tuple[float, str, float]:
    """120일선의 위치와 기울기가 일치할 때 전술 노출을 점진적으로 조절한다."""
    gap = float(row["ma_gap_120"])
    slope = float(row["ma_slope_120"])
    if gap > 0.0 and slope > 0.0:
        state, multiplier = "BULL_CONFIRMED", config.momentum_120_bull_multiplier
    elif gap < 0.0 and slope < 0.0:
        state, multiplier = "BEAR_CONFIRMED", config.momentum_120_bear_multiplier
    else:
        state, multiplier = "MIXED", 1.0
    adjusted = float(np.clip(
        tactical_target * multiplier, -config.max_short_weight, config.max_long_weight
    ))
    return adjusted, state, float(multiplier)


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
        if portfolio.risk_state in {"KILL_SWITCH_COOLDOWN", "STOP_COOLDOWN"}:
            portfolio.risk_cooldown_remaining -= 1
            portfolio.kill_switch_bars_remaining = max(portfolio.risk_cooldown_remaining, 0)
            if portfolio.risk_cooldown_remaining > 0:
                reason = "kill_switch" if portfolio.risk_state == "KILL_SWITCH_COOLDOWN" else "stop_cooldown"
                return RiskDecision(0.0, False, reason)
            portfolio.risk_state = "REENTRY_RAMP"
            portfolio.reentry_bars_elapsed = 0
            portfolio.kill_switch = False
            portfolio.kill_switch_bars_remaining = 0
            portfolio.risk_weight_cap = 1.0
            portfolio.risk_cycle_peak_equity = portfolio.equity

        # 전일 종가 자산 대비 close-to-close 손실. 시가 gap과 거래비용을 포함한다.
        daily_return = portfolio.equity / max(portfolio.previous_close_equity, EPS) - 1.0
        if daily_return <= -self.config.max_daily_loss:
            portfolio.risk_state = "STOP_COOLDOWN"
            portfolio.risk_cooldown_remaining = self.config.daily_loss_cooldown_bars
            portfolio.reentry_source = "DAILY_LOSS"
            portfolio.reentry_duration_bars = max(
                self.config.daily_loss_reentry_total_bars - self.config.daily_loss_cooldown_bars, 1
            )
            portfolio.risk_weight_cap = 0.0
            return RiskDecision(0.0, False, "daily_loss_limit")

        if portfolio.risk_state == "REENTRY_RAMP":
            return RiskDecision(0.0, True, "reentry_ramp")

        drawdown = 1.0 - portfolio.equity / max(portfolio.risk_cycle_peak_equity, EPS)
        if drawdown >= self.config.max_drawdown:
            portfolio.kill_switch = True
            portfolio.risk_state = "KILL_SWITCH_COOLDOWN"
            portfolio.risk_cooldown_remaining = self.config.kill_switch_cooldown_bars
            portfolio.reentry_source = "KILL_SWITCH"
            portfolio.reentry_duration_bars = max(
                self.config.kill_switch_reentry_total_bars - self.config.kill_switch_cooldown_bars, 1
            )
            portfolio.kill_switch_bars_remaining = portfolio.risk_cooldown_remaining
            return RiskDecision(0.0, False, "max_drawdown")

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


EMERGENCY_RISK_REASONS = {
    "kill_switch", "stop_cooldown", "max_drawdown", "daily_loss_limit"
}


def equity_weight_to_tactical(weight: float, config: Config) -> float:
    """실제 주식 비중을 0~1 전술 슬리브 신호로 역변환한다."""
    satellite = max(1.0 - config.core_equity_weight, EPS)
    return float(np.clip((weight - config.core_equity_weight) / satellite, 0.0, 1.0))


def tactical_to_equity_weight(
    tactical_weight: float, risk_reason: str, config: Config, portfolio: PortfolioState
) -> float:
    """정상 시 70~100% 코어-위성 비중, 비상 시 0%를 반환한다."""
    if risk_reason in EMERGENCY_RISK_REASONS:
        return 0.0
    if risk_reason == "reentry_ramp":
        duration = max(portfolio.reentry_duration_bars, 1)
        progress = min((portfolio.reentry_bars_elapsed + 1) / duration, 1.0)
        weight = float(config.core_equity_weight * progress)
        portfolio.reentry_bars_elapsed += 1
        if portfolio.reentry_bars_elapsed >= duration:
            portfolio.risk_state = "NORMAL"
            portfolio.risk_cycle_peak_equity = portfolio.equity
            portfolio.reentry_bars_elapsed = 0
            portfolio.reentry_source = ""
        return weight
    tactical = float(np.clip(tactical_weight, 0.0, 1.0))
    return float(config.core_equity_weight + (1.0 - config.core_equity_weight) * tactical)


class PaperBroker:
    """다음 bar Open에서 목표 비중으로 재조정하는 단순 페이퍼 브로커."""

    def __init__(self, initial_cash: float, cost_model: CostModel):
        self.state = PortfolioState(
            cash=initial_cash, equity=initial_cash, peak_equity=initial_cash,
            last_equity=initial_cash, previous_close_equity=initial_cash,
            all_time_peak_equity=initial_cash, risk_cycle_peak_equity=initial_cash,
        )
        self.cost_model = cost_model
        self.position_risk = AlgorithmPositionRiskState()

    def mark_to_market(self, close: float, timestamp: pd.Timestamp | None = None) -> None:
        self.state.equity = self.state.cash + self.state.units * close
        self.state.all_time_peak_equity = max(self.state.all_time_peak_equity, self.state.equity)
        self.state.peak_equity = self.state.all_time_peak_equity
        if self.state.risk_state in {"NORMAL", "RISK_REDUCED"}:
            self.state.risk_cycle_peak_equity = max(self.state.risk_cycle_peak_equity, self.state.equity)
        self.position_risk.observe_price(close, timestamp)

    def finalize_close(self) -> None:
        """위험 판단이 끝난 뒤 오늘 종가 자산을 다음 bar 기준값으로 확정한다."""
        self.state.last_equity = self.state.previous_close_equity
        self.state.previous_close_equity = self.state.equity

    def current_weight(self, price: float) -> float:
        return self.state.units * price / max(self.state.equity, EPS)

    def rebalance_at_open(
        self,
        target_weight: float,
        open_price: float,
        timestamp: pd.Timestamp | None = None,
    ) -> float:
        previous_units = self.state.units
        equity_before = self.state.cash + self.state.units * open_price
        desired_units = target_weight * equity_before / open_price
        traded_units = desired_units - self.state.units
        traded_notional = abs(traded_units * open_price)
        cost = traded_notional * self.cost_model.one_way_rate
        self.state.cash -= traded_units * open_price + cost
        self.state.units = desired_units
        self.state.equity = self.state.cash + self.state.units * open_price
        previous_side = np.sign(previous_units)
        next_side = np.sign(desired_units)
        if next_side == 0:
            if previous_side != 0:
                self.position_risk.status = "CLOSED"
                self.position_risk.side = "FLAT"
        elif previous_side == 0 or previous_side != next_side:
            self.position_risk.open(open_price, desired_units, timestamp)
        elif abs(desired_units) > abs(previous_units):
            added = abs(desired_units) - abs(previous_units)
            total = max(abs(desired_units), EPS)
            self.position_risk.entry_price = (
                abs(previous_units) * self.position_risk.entry_price + added * open_price
            ) / total
        return cost


# ---------------------------------------------------------------------------
# 통합 전략과 walk-forward 백테스트
# ---------------------------------------------------------------------------


class RegimeAdaptiveStrategy:
    def __init__(self, config: Config):
        self.config = config
        self.regime_engine = MarkovSwitchingRegimeEngine(config.seed, config.hmm_self_transition)
        self.lstm = LSTMExpert(lookback=20, seed=config.seed)
        self.xgb = TabularExpert("xgboost", config.seed)
        self.lgbm = TabularExpert("lightgbm", config.seed)
        self.kalman = KalmanMeanReversionExpert()
        self.ou = OUExpert()
        self.bma = BayesianModelAverager(
            config.bma_forgetting, config.bma_weight_floor, config.bma_weight_cap,
            config.bma_change_decay, config.bma_change_threshold,
            config.residual_variance_window, config.residual_variance_min_obs,
        )
        self.costs = CostModel(config)
        self.risk = RiskGate(config)
        self.last_fit_index = -10**9

    def fit(self, train: pd.DataFrame, current_index: int) -> None:
        clean = train.dropna(subset=FEATURE_COLUMNS + REGIME_FEATURE_COLUMNS + ["target"])
        if len(clean) < self.config.min_effective_train_rows:
            return
        current_regime_labels = make_current_regime_labels(clean)
        # 다음 날 방향은 레짐과 분리해 산출한다. 회귀 target 검증 및 진단에만
        # 사용하며 HMM emission의 현재 레짐 라벨로 사용하지 않는다.
        _direction_labels = make_direction_labels(clean)
        self.regime_engine.fit(clean, current_regime_labels)

        bull = clean.loc[current_regime_labels == "bull"]
        bear = clean.loc[current_regime_labels == "bear"]
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
        cash_variance = float(max(row.iloc[0]["vol_20"] ** 2, self.config.variance_floor))
        return {
            "bull_lstm": self.lstm.predict(history[FEATURE_COLUMNS].dropna()),
            "bull_xgb": self.xgb.predict(row),
            "bear_lgbm": self.lgbm.predict(row),
            "side_kalman": self.kalman.update_and_predict(float(log_prices.iloc[-1])),
            "side_ou": self.ou.predict(log_prices),
            "cash_no_trade": PredictiveDistribution(0.0, cash_variance, 0.5),
        }


def config_fingerprint(config: Config) -> str:
    return hashlib.sha256(_canonical_json(asdict(config)).encode("utf-8")).hexdigest()


def _restore_dataclass(instance: object, values: Mapping[str, object]) -> None:
    timestamp_fields = {"entry_timestamp", "cooldown_until", "last_observed_at"}
    for item in fields(instance):
        if item.name not in values:
            continue
        value = values[item.name]
        if item.name in timestamp_fields and value is not None:
            value = pd.Timestamp(value)
        if item.name == "lowest_price_since_entry" and value is None:
            value = float("inf")
        setattr(instance, item.name, value)


def build_runtime_checkpoint(
    *, date: pd.Timestamp, close: float, pending_target: float,
    broker: PaperBroker, strategy: RegimeAdaptiveStrategy, config: Config,
) -> Dict[str, object]:
    return {
        "strategy_version": "2.4",
        "config_fingerprint": config_fingerprint(config),
        "last_processed_at": pd.Timestamp(date).isoformat(),
        "last_close": float(close),
        "pending_target": float(pending_target),
        "portfolio": asdict(broker.state),
        "position_risk": asdict(broker.position_risk),
        "strategy": {
            "last_fit_index": int(strategy.last_fit_index),
            "hmm_posterior": strategy.regime_engine.posterior.tolist(),
            "hmm_last_predictive_prior": strategy.regime_engine.last_predictive_prior.tolist(),
            "bma_log_reliability": dict(strategy.bma.log_reliability),
            "bma_previous_forecasts": {
                name: asdict(pred) for name, pred in strategy.bma.previous_forecasts.items()
            },
            "bma_rolling_residuals": {
                name: list(values) for name, values in strategy.bma.rolling_residuals.items()
            },
            "bma_previous_regime_probabilities": dict(
                strategy.bma.previous_regime_probabilities
            ),
            "kalman_mean": strategy.kalman.mean,
            "kalman_state_var": float(strategy.kalman.state_var),
        },
    }


def reconcile_broker_state(
    broker: PaperBroker,
    snapshot: BrokerAccountSnapshot,
    checkpoint_date: pd.Timestamp,
    *, cash_tolerance: float = 1.0, units_tolerance: float = 1e-8,
) -> None:
    if snapshot.open_orders:
        raise ReconciliationError(
            "미체결 주문이 있어 중복 주문 위험 때문에 재개를 차단합니다: "
            + ", ".join(snapshot.open_orders)
        )
    if pd.Timestamp(snapshot.as_of).normalize() != checkpoint_date.normalize():
        raise ReconciliationError(
            f"broker snapshot 기준일({snapshot.as_of})이 checkpoint({checkpoint_date})와 다릅니다."
        )
    cash_gap = abs(float(snapshot.cash) - broker.state.cash)
    units_gap = abs(float(snapshot.units) - broker.state.units)
    if cash_gap > cash_tolerance or units_gap > units_tolerance:
        broker.state.risk_state = "RECONCILIATION_FAILED"
        broker.state.kill_switch = True
        raise ReconciliationError(
            f"계좌 대사 실패: cash_gap={cash_gap:.6f}, units_gap={units_gap:.12f}"
        )
    # 허용오차 안에서는 외부 broker가 원장(source of truth)이다.
    broker.state.cash = float(snapshot.cash)
    broker.state.units = float(snapshot.units)
    broker.state.equity = snapshot.equity
    broker.state.previous_close_equity = snapshot.equity


def restore_runtime_checkpoint(
    payload: Mapping[str, object], *, features: pd.DataFrame, prices: pd.DataFrame,
    broker: PaperBroker, strategy: RegimeAdaptiveStrategy, config: Config,
    broker_snapshot: BrokerAccountSnapshot | None,
    allow_checkpoint_only_resume: bool,
) -> Tuple[int, float]:
    if payload.get("strategy_version") != "2.4":
        raise StateIntegrityError("전략 버전이 다른 체크포인트입니다.")
    if payload.get("config_fingerprint") != config_fingerprint(config):
        raise StateIntegrityError("체크포인트와 현재 Config가 다릅니다.")
    checkpoint_date = pd.Timestamp(payload["last_processed_at"])
    if checkpoint_date not in prices.index:
        raise StateIntegrityError("체크포인트 날짜가 입력 OHLCV에 없습니다.")
    saved_close = float(payload["last_close"])
    actual_close = float(prices.at[checkpoint_date, "Close"])
    if not math.isclose(saved_close, actual_close, rel_tol=1e-10, abs_tol=1e-8):
        raise StateIntegrityError("체크포인트 종가와 입력 OHLCV 종가가 다릅니다.")

    portfolio = payload.get("portfolio")
    position_risk = payload.get("position_risk")
    strategy_state = payload.get("strategy")
    if not isinstance(portfolio, dict) or not isinstance(position_risk, dict) or not isinstance(strategy_state, dict):
        raise StateIntegrityError("체크포인트 내부 상태 형식이 잘못되었습니다.")

    fit_index = int(strategy_state["last_fit_index"])
    if fit_index >= 0:
        strategy.fit(features.iloc[: fit_index - config.horizon], fit_index)
    _restore_dataclass(broker.state, portfolio)
    _restore_dataclass(broker.position_risk, position_risk)
    strategy.last_fit_index = fit_index
    strategy.regime_engine.posterior = np.asarray(strategy_state["hmm_posterior"], dtype=float)
    strategy.regime_engine.last_predictive_prior = np.asarray(
        strategy_state["hmm_last_predictive_prior"], dtype=float
    )
    strategy.bma.log_reliability = {
        str(name): {str(regime): float(value) for regime, value in dict(values).items()}
        for name, values in dict(strategy_state["bma_log_reliability"]).items()
    }
    strategy.bma.previous_forecasts = {
        str(name): PredictiveDistribution(**values)
        for name, values in dict(strategy_state["bma_previous_forecasts"]).items()
    }
    strategy.bma.rolling_residuals = {
        str(name): [float(value) for value in values]
        for name, values in dict(strategy_state["bma_rolling_residuals"]).items()
    }
    strategy.bma.previous_regime_probabilities = {
        str(regime): float(value)
        for regime, value in dict(
            strategy_state["bma_previous_regime_probabilities"]
        ).items()
    }
    strategy.kalman.mean = strategy_state.get("kalman_mean")
    strategy.kalman.state_var = float(strategy_state["kalman_state_var"])

    if broker_snapshot is None:
        if not allow_checkpoint_only_resume:
            broker.state.risk_state = "RECONCILIATION_FAILED"
            broker.state.kill_switch = True
            raise ReconciliationError(
                "재시작에는 broker snapshot이 필요합니다. Paper 재현만 허용하려면 "
                "allow_checkpoint_only_resume=True를 명시하세요."
            )
        LOGGER.warning("외부 broker 대사 없이 checkpoint 원장만으로 재개합니다.")
    else:
        reconcile_broker_state(broker, broker_snapshot, checkpoint_date)

    location = int(features.index.get_loc(checkpoint_date))
    return location + 1, float(payload["pending_target"])


def attach_bocpd_features(features: pd.DataFrame, config: Config) -> pd.DataFrame:
    """Student-t BOCPD posterior를 과거 데이터만 사용해 순차 계산한다."""
    engine = StudentTBOCPD(
        expected_run_length=config.bocpd_expected_run_length,
        max_run_length=config.bocpd_max_run_length,
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
                "bocpd_entropy": posterior.entropy,
            }
        )
    state = pd.DataFrame(records, index=features.index)
    return features.join(state)


def run_backtest(
    ohlcv: pd.DataFrame,
    config: Config,
    loss_cut_monitor: object | None = None,
    *,
    state_store: JsonStateStore | None = None,
    resume: bool = False,
    broker_snapshot: BrokerAccountSnapshot | None = None,
    allow_checkpoint_only_resume: bool = False,
    checkpoint_every: int = 1,
) -> BacktestResult:
    validate_config(config)
    prices = validate_ohlcv(ohlcv)
    features = attach_bocpd_features(build_features(prices, config.horizon), config).join(
        prices[["Open", "High", "Low", "Close", "Volume"]]
    )
    strategy = RegimeAdaptiveStrategy(config)
    broker = PaperBroker(config.initial_cash, strategy.costs)
    rows = []

    start = max(config.min_train_rows, 80)
    pending_target = 0.0
    if checkpoint_every < 1:
        raise ValueError("checkpoint_every는 1 이상이어야 합니다.")
    if resume:
        if state_store is None:
            raise ValueError("resume=True에는 state_store가 필요합니다.")
        restored_start, pending_target = restore_runtime_checkpoint(
            state_store.load(), features=features, prices=prices,
            broker=broker, strategy=strategy, config=config,
            broker_snapshot=broker_snapshot,
            allow_checkpoint_only_resume=allow_checkpoint_only_resume,
        )
        start = max(start, restored_start)
        LOGGER.info("체크포인트 다음 bar부터 재개: %s", features.index[start] if start < len(features) else "EOF")
    processed = 0
    for i in range(start, len(features) - config.horizon):
        date = features.index[i]
        row = features.iloc[i]
        if row[FEATURE_COLUMNS].isna().any():
            continue

        # 전일 종가에 결정한 목표를 금일 시가에 집행한다.
        trading_cost = broker.rebalance_at_open(pending_target, float(row["Open"]), date)
        broker.mark_to_market(float(row["Close"]), date)
        current_weight = broker.current_weight(float(row["Close"]))

        if i - strategy.last_fit_index >= config.retrain_every:
            # 현재 행의 target은 미래를 포함하므로 학습 데이터에서 제외한다.
            strategy.fit(features.iloc[: i - config.horizon], i)

        # 직전 bar에서 만든 예측은 현재 종가에서 처음 관측 가능하다.
        # 새 가중치를 만들기 전에 갱신하여 미래 수익률 누수를 막는다.
        previous_realized = float(features.iloc[i - 1]["target"])
        if np.isfinite(previous_realized):
            strategy.bma.update(previous_realized)

        regime_p = strategy.regime_engine.predict_proba(row.to_frame().T, float(row["p_change"]))
        history = features.iloc[: i + 1]
        forecasts = strategy.forecasts(history)
        calibrated_forecasts = strategy.bma.calibrate(forecasts)
        weights = strategy.bma.weights(
            regime_p, calibrated_forecasts, float(row["p_change"])
        )
        predictive = strategy.bma.combine(calibrated_forecasts, weights)

        # Kelly와 volatility target은 30% 전술 슬리브에서만 작동한다.
        current_tactical_weight = equity_weight_to_tactical(current_weight, config)
        if predictive.valid:
            raw_target, mu_net = fractional_kelly(
                predictive, regime_p, current_tactical_weight, strategy.costs, config
            )
        else:
            raw_target, mu_net = 0.0, 0.0
        raw_target, momentum_120_state, momentum_120_multiplier = apply_120d_momentum(
            raw_target, row, config
        )
        realized_vol = float(max(row["vol_20"], 1e-4))
        decision = strategy.risk.approve(
            raw_target, current_tactical_weight, realized_vol, float(row["p_change"]), broker.state
        )
        tactical_target = decision.target_weight
        pending_target = tactical_to_equity_weight(
            tactical_target, decision.reason, config, broker.state
        )
        loss_cut = {
            "loss_cut_action": "DISABLED",
            "loss_cut_status": broker.position_risk.status,
            "loss_cut_reason": "MONITOR_NOT_CONFIGURED",
            "loss_cut_target_weight": pending_target,
            "recommended_stop_price": np.nan,
            "loss_cut_confidence": 0.0,
        }
        if loss_cut_monitor is not None:
            if not hasattr(loss_cut_monitor, "evaluate_algorithm"):
                raise TypeError("loss_cut_monitor는 evaluate_algorithm 메서드를 제공해야 합니다.")
            loss_cut = loss_cut_monitor.evaluate_algorithm(
                timestamp=date,
                market_row=row,
                current_weight=current_weight,
                approved_target_weight=pending_target,
                approved_equity_weight=pending_target,
                approved_tactical_weight=tactical_target,
                core_equity_weight=config.core_equity_weight,
                regime_probabilities=regime_p,
                predictive=predictive,
                forecasts=calibrated_forecasts,
                bma_weights=weights,
                p_change=float(row["p_change"]),
                portfolio=broker.state,
                position_state=broker.position_risk,
            )
            if bool(getattr(loss_cut_monitor, "auto_apply", False)):
                candidate = float(loss_cut["loss_cut_target_weight"])
                same_direction = candidate == 0 or pending_target == 0 or np.sign(candidate) == np.sign(pending_target)
                if same_direction and abs(candidate) <= abs(pending_target):
                    pending_target = candidate
                if broker.state.risk_state == "RISK_REDUCED":
                    pending_target = min(pending_target, broker.state.risk_weight_cap)

        rows.append(
            {
                "date": date,
                "equity": broker.state.equity,
                "current_weight": current_weight,
                "target_weight": pending_target,
                "core_equity_weight": config.core_equity_weight,
                "current_tactical_weight": current_tactical_weight,
                "tactical_target_weight": tactical_target,
                "risk_state": broker.state.risk_state,
                "risk_cooldown_remaining": broker.state.risk_cooldown_remaining,
                "reentry_source": broker.state.reentry_source,
                "reentry_duration_bars": broker.state.reentry_duration_bars,
                "risk_weight_cap": broker.state.risk_weight_cap,
                "all_time_peak_equity": broker.state.all_time_peak_equity,
                "risk_cycle_peak_equity": broker.state.risk_cycle_peak_equity,
                "p_change": row["p_change"],
                "engine_regime": max(regime_p, key=regime_p.get),
                "expected_run_length": row["run_length"],
                "bocpd_entropy": row["bocpd_entropy"],
                **{
                    f"hmm_prior_{name}": strategy.regime_engine.last_predictive_prior[j]
                    for j, name in enumerate(REGIMES)
                },
                **{f"p_{k}": v for k, v in regime_p.items()},
                "forecast_mean": predictive.mean,
                "forecast_variance": predictive.variance,
                "mu_net": mu_net,
                "momentum_120_state": momentum_120_state,
                "momentum_120_multiplier": momentum_120_multiplier,
                "trading_cost": trading_cost,
                "risk_reason": decision.reason,
                **loss_cut,
                "bma_weights": json.dumps(weights, ensure_ascii=False),
                "bma_reliability_by_regime": json.dumps(
                    strategy.bma.log_reliability, ensure_ascii=False
                ),
                "expert_oos_variances": json.dumps(
                    {
                        name: float(pred.variance)
                        for name, pred in calibrated_forecasts.items()
                    },
                    ensure_ascii=False,
                ),
            }
        )
        broker.finalize_close()
        processed += 1
        if state_store is not None and processed % checkpoint_every == 0:
            state_store.save(build_runtime_checkpoint(
                date=date, close=float(row["Close"]), pending_target=pending_target,
                broker=broker, strategy=strategy, config=config,
            ))

    if not rows:
        empty = pd.Series(dtype=float)
        return BacktestResult(empty.rename("equity"), empty.rename("returns"), pd.DataFrame(), {})
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


def load_loss_cut_monitor(
    auto_apply: bool = False, cooldown_bars: int = 1, reentry_total_bars: int = 3
) -> object:
    """같은 폴더의 ``Algorithm(ver.2.4)_loss_cut.py``를 동적으로 로드한다."""
    import importlib.util
    import sys

    companion = Path(__file__).with_name(f"{Path(__file__).stem}_loss_cut.py")
    if not companion.exists():
        raise FileNotFoundError(f"손절 companion 모듈이 없습니다: {companion}")
    module_name = "algorithm_ver_2_4_loss_cut"
    spec = importlib.util.spec_from_file_location(module_name, companion)
    if spec is None or spec.loader is None:
        raise ImportError(f"손절 companion 모듈을 로드할 수 없습니다: {companion}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    config = module.AlgorithmLossCutConfig(
        auto_apply=auto_apply, cooldown_bars=cooldown_bars,
        reentry_total_bars=reentry_total_bars,
    )
    return module.AlgorithmLossCutMonitor(config)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BOCPD-HMM-LightGBM 레짐 적응형 자동매매 참조 구현")
    parser.add_argument("--csv", type=Path, help="Date/Open/High/Low/Close/Volume CSV")
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--output", type=Path, help="의사결정 로그 CSV 저장 경로")
    parser.add_argument("--rows", type=int, default=1_500, help="합성 데이터 행 수")
    parser.add_argument("--state-file", type=Path, help="원자적으로 저장할 runtime checkpoint JSON")
    parser.add_argument("--resume", action="store_true", help="state-file 다음 bar부터 재개")
    parser.add_argument("--broker-snapshot", type=Path, help="재시작 대사용 cash/units/last_price/as_of JSON")
    parser.add_argument(
        "--allow-checkpoint-only-resume", action="store_true",
        help="외부 계좌 대사 없이 paper checkpoint만 신뢰해 재개(실거래 비권장)",
    )
    parser.add_argument("--checkpoint-every", type=int, default=1, help="N개 처리 bar마다 상태 저장")
    parser.add_argument("--enable-loss-cut", action="store_true", help="별도 손절 모니터 활성화")
    parser.add_argument(
        "--auto-apply-loss-cut",
        action="store_true",
        help="손절 권고가 기존 목표보다 보수적일 때 다음 목표 비중에 자동 반영",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = Config(initial_cash=args.initial_cash)
    data = pd.read_csv(args.csv) if args.csv else make_synthetic_ohlcv(args.rows, config.seed)
    data = validate_ohlcv(data)
    LOGGER.info("백테스트 시작: %s ~ %s, %d bars", data.index.min().date(), data.index.max().date(), len(data))
    monitor = (
        load_loss_cut_monitor(
            args.auto_apply_loss_cut, config.stop_cooldown_bars,
            config.stop_reentry_total_bars,
        )
        if args.enable_loss_cut else None
    )
    store = JsonStateStore(args.state_file) if args.state_file else None
    snapshot = BrokerAccountSnapshot.from_json_file(args.broker_snapshot) if args.broker_snapshot else None
    result = run_backtest(
        data, config, loss_cut_monitor=monitor, state_store=store,
        resume=args.resume, broker_snapshot=snapshot,
        allow_checkpoint_only_resume=args.allow_checkpoint_only_resume,
        checkpoint_every=args.checkpoint_every,
    )
    print(json.dumps(result.metrics, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result.decisions.to_csv(args.output, encoding="utf-8-sig")
        LOGGER.info("의사결정 로그 저장: %s", args.output.resolve())


if __name__ == "__main__":
    main()
