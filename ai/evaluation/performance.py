"""일별 수익률 또는 자산 곡선에서 전략 성과 지표를 계산한다."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PerformanceMetrics:
    """API와 리포트에서 직렬화할 수 있는 핵심 전략 성과 지표다."""

    cumulative_return: float
    cagr: float
    annualized_volatility: float
    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown: float
    win_rate: float
    profit_factor: float | None
    observation_count: int
    periods_per_year: int

    def __post_init__(self) -> None:
        for name in (
            "cumulative_return",
            "cagr",
            "annualized_volatility",
            "sharpe_ratio",
            "sortino_ratio",
            "max_drawdown",
            "win_rate",
            "profit_factor",
        ):
            value = getattr(self, name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"calculated metric {name} must be finite")

    def to_dict(self) -> dict[str, Any]:
        """JSON encoder에 바로 전달할 수 있는 기본 타입 사전을 반환한다."""

        return asdict(self)


def _validate_series(values: pd.Series, *, name: str) -> pd.Series:
    if not isinstance(values, pd.Series):
        raise TypeError(f"{name} must be a pandas Series")
    if values.empty:
        raise ValueError(f"{name} cannot be empty")
    if not values.index.is_unique:
        raise ValueError(f"{name} index must be unique")
    if not values.index.is_monotonic_increasing:
        raise ValueError(f"{name} index must be sorted in ascending order")

    numeric = pd.to_numeric(values, errors="coerce").astype(float)
    if numeric.isna().any() or not np.isfinite(numeric.to_numpy()).all():
        raise ValueError(f"{name} must contain only finite numeric values")
    return numeric


def _returns_and_wealth(
    *,
    daily_returns: pd.Series | None,
    equity_curve: pd.Series | None,
) -> tuple[pd.Series, pd.Series]:
    if (daily_returns is None) == (equity_curve is None):
        raise ValueError("provide exactly one of daily_returns or equity_curve")

    if daily_returns is not None:
        returns = _validate_series(daily_returns, name="daily_returns")
        if returns.le(-1.0).any():
            raise ValueError("daily_returns must be greater than -1")
        wealth = pd.concat([
            pd.Series([1.0], dtype=float),
            (1.0 + returns).cumprod().reset_index(drop=True),
        ], ignore_index=True)
        return returns, wealth

    equity = _validate_series(equity_curve, name="equity_curve")
    if equity.le(0.0).any():
        raise ValueError("equity_curve must contain only positive values")
    if len(equity) < 2:
        raise ValueError("equity_curve must contain at least two observations")

    returns = equity.pct_change(fill_method=None).iloc[1:]
    returns.name = "daily_return"
    wealth = (equity / float(equity.iloc[0])).reset_index(drop=True)
    return returns, wealth


def calculate_performance_metrics(
    *,
    daily_returns: pd.Series | None = None,
    equity_curve: pd.Series | None = None,
    periods_per_year: int = 252,
    annual_risk_free_rate: float = 0.0,
) -> PerformanceMetrics:
    """핵심 백테스트 성과 지표를 일별 관측치 기준으로 계산한다.

    ``daily_returns``와 ``equity_curve`` 중 하나만 전달해야 한다. CAGR은 실제
    관측 구간 수를 ``periods_per_year``로 나눈 기간을 사용한다. Sharpe는 일별
    초과수익률의 표본 표준편차, Sortino는 0 미만 초과수익률의 하방 편차를
    사용한다. 분모가 0인 비율 지표는 JSON 비호환 무한대 대신 ``None``이다.
    """

    if not isinstance(periods_per_year, int) or isinstance(periods_per_year, bool):
        raise TypeError("periods_per_year must be an integer")
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    if not math.isfinite(annual_risk_free_rate) or annual_risk_free_rate <= -1.0:
        raise ValueError("annual_risk_free_rate must be finite and greater than -1")

    returns, wealth = _returns_and_wealth(
        daily_returns=daily_returns,
        equity_curve=equity_curve,
    )
    observation_count = len(returns)
    cumulative_return = float(wealth.iloc[-1] / wealth.iloc[0] - 1.0)
    years = observation_count / periods_per_year
    cagr = float((1.0 + cumulative_return) ** (1.0 / years) - 1.0)

    if observation_count >= 2:
        daily_volatility = float(returns.std(ddof=1))
        annualized_volatility = daily_volatility * math.sqrt(periods_per_year)
    else:
        daily_volatility = 0.0
        annualized_volatility = 0.0

    daily_risk_free_rate = (1.0 + annual_risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    excess_returns = returns - daily_risk_free_rate
    sharpe_ratio = None
    if daily_volatility > 0.0:
        sharpe_ratio = float(
            excess_returns.mean() / daily_volatility * math.sqrt(periods_per_year)
        )

    downside = np.minimum(excess_returns.to_numpy(dtype=float), 0.0)
    downside_deviation = float(np.sqrt(np.mean(np.square(downside))))
    sortino_ratio = None
    if downside_deviation > 0.0:
        sortino_ratio = float(
            excess_returns.mean() / downside_deviation * math.sqrt(periods_per_year)
        )

    drawdown = wealth / wealth.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    win_rate = float(returns.gt(0.0).mean())
    gross_profit = float(returns.clip(lower=0.0).sum())
    gross_loss = float(-returns.clip(upper=0.0).sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0.0 else None

    return PerformanceMetrics(
        cumulative_return=cumulative_return,
        cagr=cagr,
        annualized_volatility=float(annualized_volatility),
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        profit_factor=float(profit_factor) if profit_factor is not None else None,
        observation_count=observation_count,
        periods_per_year=periods_per_year,
    )
