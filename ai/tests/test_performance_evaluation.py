import json
import math

import numpy as np
import pandas as pd
import pytest

from evaluation import PerformanceMetrics, calculate_performance_metrics


def test_calculates_core_metrics_from_daily_returns() -> None:
    returns = pd.Series([0.10, -0.05, 0.02, -0.01], name="daily_return")

    metrics = calculate_performance_metrics(
        daily_returns=returns,
        periods_per_year=4,
    )

    expected_wealth = (1.0 + returns).cumprod()
    expected_cumulative = float(expected_wealth.iloc[-1] - 1.0)
    expected_volatility = float(returns.std(ddof=1) * math.sqrt(4))
    expected_sharpe = float(returns.mean() / returns.std(ddof=1) * math.sqrt(4))
    downside = np.minimum(returns.to_numpy(), 0.0)
    expected_sortino = float(returns.mean() / np.sqrt(np.mean(downside**2)) * math.sqrt(4))
    wealth_with_origin = pd.Series([1.0, *expected_wealth.tolist()])
    expected_mdd = float((wealth_with_origin / wealth_with_origin.cummax() - 1.0).min())

    assert isinstance(metrics, PerformanceMetrics)
    assert metrics.cumulative_return == pytest.approx(expected_cumulative)
    assert metrics.cagr == pytest.approx(expected_cumulative)
    assert metrics.annualized_volatility == pytest.approx(expected_volatility)
    assert metrics.sharpe_ratio == pytest.approx(expected_sharpe)
    assert metrics.sortino_ratio == pytest.approx(expected_sortino)
    assert metrics.max_drawdown == pytest.approx(expected_mdd)
    assert metrics.win_rate == pytest.approx(0.5)
    assert metrics.profit_factor == pytest.approx(0.12 / 0.06)
    assert metrics.observation_count == 4
    assert metrics.periods_per_year == 4


def test_equity_curve_and_daily_returns_produce_same_metrics() -> None:
    returns = pd.Series(
        [0.03, -0.01, 0.02, -0.04, 0.01],
        index=pd.date_range("2026-01-02", periods=5, freq="B"),
    )
    equity = pd.Series(
        [100.0, *((1.0 + returns).cumprod() * 100.0).tolist()],
        index=pd.date_range("2026-01-01", periods=6, freq="B"),
    )

    from_returns = calculate_performance_metrics(daily_returns=returns)
    from_equity = calculate_performance_metrics(equity_curve=equity)

    assert from_equity.to_dict() == pytest.approx(from_returns.to_dict())


def test_constant_positive_returns_use_none_for_undefined_ratios() -> None:
    metrics = calculate_performance_metrics(
        daily_returns=pd.Series([0.01, 0.01, 0.01]),
    )

    json.dumps(metrics.to_dict(), allow_nan=False)
    assert metrics.sharpe_ratio is None
    assert metrics.sortino_ratio is None
    assert metrics.profit_factor is None
    assert metrics.max_drawdown == pytest.approx(0.0)
    assert metrics.win_rate == pytest.approx(1.0)


def test_all_loss_returns_have_zero_profit_factor_and_win_rate() -> None:
    metrics = calculate_performance_metrics(
        daily_returns=pd.Series([-0.01, -0.02, -0.03]),
    )

    assert metrics.profit_factor == pytest.approx(0.0)
    assert metrics.win_rate == pytest.approx(0.0)
    assert metrics.max_drawdown < 0.0


def test_annual_risk_free_rate_is_applied_to_ratio_numerators() -> None:
    returns = pd.Series([0.01, 0.02, -0.01, 0.00])
    periods = 4
    annual_rate = 0.08
    daily_rate = (1.0 + annual_rate) ** (1.0 / periods) - 1.0

    metrics = calculate_performance_metrics(
        daily_returns=returns,
        periods_per_year=periods,
        annual_risk_free_rate=annual_rate,
    )

    expected = float(
        (returns - daily_rate).mean() / returns.std(ddof=1) * math.sqrt(periods)
    )
    assert metrics.sharpe_ratio == pytest.approx(expected)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "provide exactly one"),
        ({"daily_returns": pd.Series([0.01]), "equity_curve": pd.Series([1.0, 1.01])}, "provide exactly one"),
        ({"daily_returns": pd.Series(dtype=float)}, "cannot be empty"),
        ({"daily_returns": pd.Series([0.01, np.nan])}, "finite numeric"),
        ({"daily_returns": pd.Series([0.01, np.inf])}, "finite numeric"),
        ({"daily_returns": pd.Series([-1.0])}, "greater than -1"),
        ({"equity_curve": pd.Series([100.0])}, "at least two"),
        ({"equity_curve": pd.Series([100.0, 0.0])}, "positive values"),
    ],
)
def test_rejects_invalid_metric_inputs(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        calculate_performance_metrics(**kwargs)


def test_rejects_unsorted_or_duplicate_index() -> None:
    unsorted = pd.Series([0.01, 0.02], index=[2, 1])
    duplicate = pd.Series([0.01, 0.02], index=[1, 1])

    with pytest.raises(ValueError, match="sorted"):
        calculate_performance_metrics(daily_returns=unsorted)
    with pytest.raises(ValueError, match="unique"):
        calculate_performance_metrics(daily_returns=duplicate)


@pytest.mark.parametrize("periods_per_year", [0, -1])
def test_rejects_non_positive_annualization(periods_per_year: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        calculate_performance_metrics(
            daily_returns=pd.Series([0.01]),
            periods_per_year=periods_per_year,
        )
