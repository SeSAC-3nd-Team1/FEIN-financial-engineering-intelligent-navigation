"""Quarterly point-in-time comparison of momentum v1, momentum v2, and KOSPI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math

import numpy as np
import pandas as pd

from evaluation.performance import PerformanceMetrics, calculate_performance_metrics
from inference.risk_adjusted_recommendation_snapshot import (
    _capped_score_market_cap_weights,
)
from models.risk_adjusted_momentum import (
    RiskAdjustedMomentumConfig,
    RiskAdjustedMomentumModel,
)


class BacktestUnavailableError(RuntimeError):
    """Raised instead of publishing performance from unsafe unadjusted prices."""


@dataclass(frozen=True)
class StrategyBacktestResult:
    model_version: str
    metrics: PerformanceMetrics
    average_turnover: float
    total_turnover: float
    rebalance_count: int
    transaction_cost_bps: float

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["metrics"] = self.metrics.to_dict()
        return payload


@dataclass(frozen=True)
class MomentumComparisonResult:
    start_date: str
    end_date: str
    rebalance_frequency: str
    price_policy: str
    price_momentum_v1: StrategyBacktestResult
    risk_adjusted_momentum_v2: StrategyBacktestResult
    kospi: StrategyBacktestResult

    def to_dict(self) -> dict[str, object]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "rebalance_frequency": self.rebalance_frequency,
            "price_policy": self.price_policy,
            "price_momentum_v1": self.price_momentum_v1.to_dict(),
            "risk_adjusted_momentum_v2": self.risk_adjusted_momentum_v2.to_dict(),
            "kospi": self.kospi.to_dict(),
        }


def _quarter_ends(dates: pd.Series) -> list[pd.Timestamp]:
    unique = pd.Series(pd.to_datetime(dates).dropna().unique()).sort_values()
    return unique.groupby([unique.dt.year, unique.dt.quarter]).max().tolist()


def _v1_target(cross_section: pd.DataFrame, universe_size: int = 100) -> dict[str, float]:
    eligible = cross_section["is_tradable"].fillna(False).astype(bool) & cross_section[
        "risk_eligible"
    ].fillna(False).astype(bool)
    data = cross_section.loc[
        eligible
        & pd.to_numeric(cross_section["market_cap"], errors="coerce").gt(0)
        & pd.to_numeric(cross_section["momentum_120d"], errors="coerce").notna()
    ].copy()
    selected = (
        data.sort_values(["market_cap", "stock_code"], ascending=[False, True])
        .head(universe_size)
        .sort_values(["momentum_120d", "stock_code"], ascending=[False, True])
        .head(5)
    )
    if len(selected) < 5:
        raise BacktestUnavailableError("v1 has fewer than five eligible stocks")
    return {str(symbol): 0.19 for symbol in selected["stock_code"]}


def _v2_target(
    model: RiskAdjustedMomentumModel, cross_section: pd.DataFrame
) -> dict[str, float]:
    ranked = model.rank(cross_section)
    selected = ranked.loc[ranked["selected"]].copy()
    if len(selected) < model.config.min_positions:
        raise BacktestUnavailableError("v2 has too few eligible stocks for the 5% cap")
    return {
        symbol: float(weight)
        for symbol, weight in _capped_score_market_cap_weights(selected).items()
        if weight > 0
    }


def _turnover(previous: dict[str, float], target: dict[str, float]) -> float:
    symbols = set(previous) | set(target)
    stock = sum(abs(target.get(symbol, 0.0) - previous.get(symbol, 0.0)) for symbol in symbols)
    cash = abs((1.0 - sum(target.values())) - (1.0 - sum(previous.values())))
    return (stock + cash) / 2.0


def _apply_daily_returns(
    weights: dict[str, float],
    observed_returns: pd.Series,
    *,
    transaction_cost: float = 0.0,
) -> tuple[float, dict[str, float]]:
    """Apply one day's returns and preserve the resulting portfolio-weight drift."""

    cash_weight = 1.0 - sum(weights.values())
    closing_stock_values = {
        symbol: weight * (1.0 + float(observed_returns[symbol]))
        for symbol, weight in weights.items()
    }
    closing_portfolio_value = (
        cash_weight + sum(closing_stock_values.values()) - transaction_cost
    )
    if not math.isfinite(closing_portfolio_value) or closing_portfolio_value <= 0:
        raise BacktestUnavailableError("portfolio value became non-positive or non-finite")
    closing_weights = {
        symbol: value / closing_portfolio_value
        for symbol, value in closing_stock_values.items()
        if value > 0
    }
    return closing_portfolio_value - 1.0, closing_weights


def _run_strategy(
    history: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
    target_builder,
    *,
    model_version: str,
    transaction_cost_bps: float,
) -> tuple[StrategyBacktestResult, pd.Series]:
    data = history.sort_values(["trade_date", "stock_code"]).copy()
    price_column = (
        "point_in_time_adjusted_close"
        if "point_in_time_adjusted_close" in data
        else "close_price"
    )
    prices = data.pivot(index="trade_date", columns="stock_code", values=price_column).sort_index()
    shares = data.pivot(index="trade_date", columns="stock_code", values="listed_shares").sort_index()
    event_safe = data.pivot(
        index="trade_date", columns="stock_code", values="corporate_action_event_safe"
    ).sort_index()
    daily_returns = prices.pct_change(fill_method=None)
    weights: dict[str, float] = {}
    pending_cost = 0.0
    turnovers: list[float] = []
    realized: list[tuple[pd.Timestamp, float]] = []
    rebalance_set = set(rebalance_dates)

    for trade_date in prices.index:
        if weights:
            symbols = list(weights)
            observed = daily_returns.loc[trade_date, symbols]
            unsafe = shares.loc[trade_date, symbols].isna() | ~event_safe.loc[
                trade_date, symbols
            ].eq(True)
            if unsafe.any():
                bad = ", ".join(unsafe.index[unsafe].astype(str)[:5])
                raise BacktestUnavailableError(
                    f"unresolved held-security corporate-action or missing observation "
                    f"on {trade_date.date()}: {bad}"
                )
            if observed.isna().any():
                raise BacktestUnavailableError(
                    f"held-security return missing on {trade_date.date()}"
                )
            net_return, weights = _apply_daily_returns(
                weights, observed, transaction_cost=pending_cost
            )
            realized.append((trade_date, net_return))
            pending_cost = 0.0

        if trade_date in rebalance_set:
            cross_section = data.loc[data["trade_date"].eq(trade_date)].copy()
            target = target_builder(cross_section)
            one_way = _turnover(weights, target)
            turnovers.append(one_way)
            pending_cost = one_way * transaction_cost_bps / 10_000.0
            weights = target

    if len(realized) < 2:
        raise BacktestUnavailableError("backtest has fewer than two realized return observations")
    returns = pd.Series(dict(realized), dtype=float).sort_index()
    metrics = calculate_performance_metrics(daily_returns=returns)
    result = StrategyBacktestResult(
        model_version=model_version,
        metrics=metrics,
        average_turnover=float(np.mean(turnovers)) if turnovers else 0.0,
        total_turnover=float(sum(turnovers)),
        rebalance_count=len(turnovers),
        transaction_cost_bps=transaction_cost_bps,
    )
    return result, returns


def compare_momentum_strategies(
    stock_history: pd.DataFrame,
    benchmark_history: pd.DataFrame,
    *,
    benchmark_name: str = "코스피",
    transaction_cost_bps: float = 0.0,
    evaluation_start: str | pd.Timestamp | None = None,
    evaluation_end: str | pd.Timestamp | None = None,
    config: RiskAdjustedMomentumConfig = RiskAdjustedMomentumConfig(),
) -> MomentumComparisonResult:
    """Compare all legs on common quarterly dates; forward returns are evaluation-only."""

    if not math.isfinite(transaction_cost_bps) or transaction_cost_bps < 0:
        raise ValueError("transaction_cost_bps must be finite and non-negative")
    required = {
        "stock_code", "trade_date", "close_price", "listed_shares", "market_cap",
        "momentum_120d", "is_tradable", "risk_eligible",
    }
    missing = sorted(required - set(stock_history.columns))
    if missing:
        raise ValueError(f"backtest stock columns missing: {missing}")
    history = stock_history.copy()
    history["trade_date"] = pd.to_datetime(history["trade_date"], errors="raise")
    model = RiskAdjustedMomentumModel(config)
    features = model.compute_features(history)

    benchmark = benchmark_history.copy()
    benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"], errors="raise")
    benchmark = benchmark.loc[benchmark["index_name"].eq(benchmark_name)].copy()
    benchmark["close_index"] = pd.to_numeric(benchmark["close_index"], errors="coerce")
    benchmark = benchmark.dropna(subset=["trade_date", "close_index"]).sort_values("trade_date")
    if benchmark.empty:
        raise BacktestUnavailableError(f"benchmark index not found: {benchmark_name}")

    benchmark_dates = set(benchmark["trade_date"])
    start_boundary = (
        pd.Timestamp(evaluation_start) if evaluation_start is not None else None
    )
    end_boundary = pd.Timestamp(evaluation_end) if evaluation_end is not None else None
    common_rebalances: list[pd.Timestamp] = []
    for candidate in _quarter_ends(features["trade_date"]):
        if start_boundary is not None and candidate < start_boundary:
            continue
        if end_boundary is not None and candidate > end_boundary:
            continue
        if candidate not in benchmark_dates:
            continue
        cross = features.loc[features["trade_date"].eq(candidate)]
        try:
            _v1_target(cross, config.universe_size)
            _v2_target(model, cross)
        except BacktestUnavailableError:
            continue
        common_rebalances.append(candidate)
    if not common_rebalances:
        raise BacktestUnavailableError("no common quarterly rebalance date has valid v1 and v2 portfolios")

    start = common_rebalances[0]
    end = min(features["trade_date"].max(), benchmark["trade_date"].max())
    if end_boundary is not None:
        end = min(end, end_boundary)
    common_rebalances = [date for date in common_rebalances if date <= end]
    test_history = features.loc[features["trade_date"].between(start, end)].copy()
    v1, v1_returns = _run_strategy(
        test_history, common_rebalances, lambda cross: _v1_target(cross, config.universe_size),
        model_version="price-momentum-v1", transaction_cost_bps=transaction_cost_bps,
    )
    v2, v2_returns = _run_strategy(
        test_history, common_rebalances, lambda cross: _v2_target(model, cross),
        model_version=RiskAdjustedMomentumModel.MODEL_VERSION,
        transaction_cost_bps=transaction_cost_bps,
    )
    evaluation_dates = v1_returns.index.intersection(v2_returns.index)
    benchmark_returns = (
        benchmark.set_index("trade_date")["close_index"].pct_change(fill_method=None)
        .reindex(evaluation_dates).dropna()
    )
    evaluation_dates = evaluation_dates.intersection(benchmark_returns.index)
    if len(evaluation_dates) < 2:
        raise BacktestUnavailableError("benchmark has insufficient common evaluation dates")
    benchmark_metrics = calculate_performance_metrics(
        daily_returns=benchmark_returns.reindex(evaluation_dates)
    )
    v1 = replace(
        v1,
        metrics=calculate_performance_metrics(
            daily_returns=v1_returns.reindex(evaluation_dates)
        ),
    )
    v2 = replace(
        v2,
        metrics=calculate_performance_metrics(
            daily_returns=v2_returns.reindex(evaluation_dates)
        ),
    )
    kospi = StrategyBacktestResult(
        model_version=benchmark_name,
        metrics=benchmark_metrics,
        average_turnover=0.0,
        total_turnover=0.0,
        rebalance_count=0,
        transaction_cost_bps=0.0,
    )
    return MomentumComparisonResult(
        start_date=pd.Timestamp(evaluation_dates.min()).date().isoformat(),
        end_date=pd.Timestamp(evaluation_dates.max()).date().isoformat(),
        rebalance_frequency="QUARTERLY",
        price_policy="point-in-time split-adjusted; fail-closed on unresolved held-security events",
        price_momentum_v1=v1,
        risk_adjusted_momentum_v2=v2,
        kospi=kospi,
    )
