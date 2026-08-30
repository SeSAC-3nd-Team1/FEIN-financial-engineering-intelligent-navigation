"""시장 대비 10% 상대성과를 *가정*하는 오라클형 통합시험 MOCK.

이 파일은 Algorithm(ver.0).py와 같은 핵심 입출력 API(`Config`,
`BacktestResult`, `run_backtest`)를 제공합니다. 미래 종가를 이용해 사후적으로
성과를 구성하므로 예측 모델, 투자 전략 또는 수익 보장이 아닙니다. 실거래 금지.

CSV 필수 열: Date, Open, High, Low, Close, Volume
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

MOCK_OUTPERFORMANCE_FACTOR = 1.10
MOCK_STATUS = "MOCK_ORACLE_NON_CAUSAL_DO_NOT_TRADE"


@dataclass(frozen=True)
class Config:
    seed: int = 42
    horizon: int = 1
    min_train_rows: int = 252
    retrain_every: int = 63
    bocpd_max_run_length: int = 180
    bocpd_expected_run_length: int = 60
    regime_smoothing: float = 0.25
    cp_fast_smoothing: float = 0.70
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
    reason: str = MOCK_STATUS


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
    kill_switch: bool = False


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    decisions: pd.DataFrame
    metrics: Dict[str, float]


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


def make_synthetic_ohlcv(n: int = 1500, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.00025, 0.012, n)
    close = 100.0 * np.exp(np.cumsum(ret))
    spread = rng.uniform(0.002, 0.018, n)
    index = pd.bdate_range("2018-01-02", periods=n)
    return pd.DataFrame({
        "Open": close * (1 + rng.normal(0, 0.002, n)),
        "High": close * (1 + spread),
        "Low": close * (1 - spread),
        "Close": close,
        "Volume": rng.integers(100_000, 2_000_000, n),
    }, index=index)


def _metrics(returns: pd.Series, equity: pd.Series) -> Dict[str, float]:
    years = max(len(returns) / 252.0, 1.0 / 252.0)
    total = float(equity.iloc[-1] / equity.iloc[0] * (1 + returns.iloc[0]) - 1)
    vol = float(returns.std(ddof=0) * math.sqrt(252))
    sharpe = float(returns.mean() / returns.std(ddof=0) * math.sqrt(252)) if returns.std(ddof=0) > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    return {
        "final_equity": float(equity.iloc[-1]),
        "total_return": total,
        "cagr": float((1 + total) ** (1 / years) - 1),
        "annual_volatility": vol,
        "sharpe_zero_rf": sharpe,
        "max_drawdown": float(drawdown.min()),
        "total_trading_cost": 0.0,
        "bars": float(len(returns)),
    }


def run_backtest(ohlcv: pd.DataFrame, config: Config = Config()) -> BacktestResult:
    """검증 구간에서 시장 최종 부의 정확히 1.10배를 만드는 MOCK 결과를 반환한다.

    입력 OHLCV의 Close 수익률을 시장 대용치로 사용한다. 합성 알파는 사후 계산되고
    거래비용 차감 후 수익률로 간주되므로 이 함수는 오직 파이프라인 테스트용이다.
    """
    df = validate_ohlcv(ohlcv)
    start = max(int(config.min_train_rows), 1)
    if len(df) <= start:
        raise ValueError(f"최소 {start + 1}개 행이 필요합니다.")
    market_returns = df["Close"].pct_change().iloc[start:].astype(float)
    n = len(market_returns)
    daily_alpha = MOCK_OUTPERFORMANCE_FACTOR ** (1.0 / n) - 1.0
    mock_returns = (1.0 + market_returns) * (1.0 + daily_alpha) - 1.0
    benchmark_equity = config.initial_cash * (1.0 + market_returns).cumprod()
    equity = config.initial_cash * (1.0 + mock_returns).cumprod()
    relative_wealth = equity / benchmark_equity
    rolling_vol = market_returns.rolling(20, min_periods=2).var().fillna(config.variance_floor)
    decisions = pd.DataFrame(index=market_returns.index)
    decisions["equity"] = equity
    decisions["current_weight"] = 1.0
    decisions["target_weight"] = 1.0
    decisions["p_change"] = 0.0
    decisions["p_bull"] = 1.0 / 3.0
    decisions["p_bear"] = 1.0 / 3.0
    decisions["p_sideways"] = 1.0 / 3.0
    decisions["forecast_mean"] = mock_returns
    decisions["forecast_variance"] = rolling_vol.clip(lower=config.variance_floor)
    decisions["mu_net"] = mock_returns
    decisions["trading_cost"] = 0.0
    decisions["risk_reason"] = MOCK_STATUS
    decisions["bma_weights"] = json.dumps({"mock_oracle": 1.0})
    decisions["benchmark_return"] = market_returns
    decisions["benchmark_equity"] = benchmark_equity
    decisions["mock_alpha_daily"] = daily_alpha
    decisions["relative_wealth"] = relative_wealth
    decisions["is_mock"] = True
    metrics = _metrics(mock_returns, equity)
    market_total = float(benchmark_equity.iloc[-1] / config.initial_cash - 1.0)
    metrics.update({
        "benchmark_final_equity": float(benchmark_equity.iloc[-1]),
        "benchmark_total_return": market_total,
        "relative_wealth_factor": float(relative_wealth.iloc[-1]),
        "relative_outperformance": float(relative_wealth.iloc[-1] - 1.0),
        "mock_daily_alpha": float(daily_alpha),
    })
    return BacktestResult(equity.rename("equity"), mock_returns.rename("return"), decisions, metrics)


def load_companion(suffix: str):
    path = Path(__file__).with_name(f"MOCK_{suffix}.py")
    spec = importlib.util.spec_from_file_location(f"mock_{suffix}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"모듈을 불러올 수 없습니다: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_with_loss_cut(ohlcv: pd.DataFrame, config: Config = Config()) -> BacktestResult:
    result = run_backtest(ohlcv, config)
    monitor = load_companion("loss_cut").MockLossCutMonitor()
    result.decisions = monitor.annotate_decisions(result.decisions, validate_ohlcv(ohlcv))
    return result


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="10% 상대성과 오라클 MOCK (실거래 금지)")
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--output", type=Path, default=Path("MOCK_decisions.csv"))
    parser.add_argument("--rows", type=int, default=1500)
    args = parser.parse_args(argv)
    data = pd.read_csv(args.csv) if args.csv else make_synthetic_ohlcv(args.rows)
    result = run_with_loss_cut(data, Config(initial_cash=args.initial_cash))
    result.decisions.to_csv(args.output, index_label="Date")
    print(MOCK_STATUS)
    print(json.dumps(result.metrics, ensure_ascii=False, indent=2))
    print(f"saved: {args.output.resolve()}")


if __name__ == "__main__":
    main()
