import math

import pandas as pd
import pytest

from evaluation.momentum_backtest import (
    BacktestUnavailableError,
    _apply_daily_returns,
    compare_momentum_strategies,
)
from models.risk_adjusted_momentum import RiskAdjustedMomentumConfig


CONFIG = RiskAdjustedMomentumConfig(
    skip_trading_days=2,
    six_month_trading_days=5,
    twelve_month_trading_days=10,
    weekly_volatility_observations=2,
    universe_size=25,
    selection_fraction=0.8,
    min_positions=19,
    max_positions=20,
)


def stock_history(periods: int = 300) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=periods)
    rows = []
    for number in range(25):
        for offset, trade_date in enumerate(dates):
            growth = (number + 1) / 100_000
            close = 10_000 * (1 + growth) ** offset * (
                1 + 0.002 * math.sin(offset / 3 + number)
            )
            rows.append(
                {
                    "stock_code": f"S{number:05d}",
                    "trade_date": trade_date,
                    "close_price": close,
                    "listed_shares": 1_000_000,
                    "market_cap": close * 1_000_000,
                    "momentum_120d": (number + 1) / 100,
                    "is_tradable": True,
                    "risk_eligible": True,
                }
            )
    return pd.DataFrame(rows)


def benchmark(periods: int = 300) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=periods)
    return pd.DataFrame(
        {
            "trade_date": dates,
            "index_name": "코스피",
            "close_index": [2500 * 1.0001**offset for offset in range(periods)],
        }
    )


def test_quarterly_backtest_compares_v1_v2_and_kospi_without_lookahead() -> None:
    result = compare_momentum_strategies(
        stock_history(), benchmark(), config=CONFIG, transaction_cost_bps=10
    )

    assert result.rebalance_frequency == "QUARTERLY"
    assert result.price_momentum_v1.model_version == "price-momentum-v1"
    assert result.risk_adjusted_momentum_v2.model_version == "risk-adjusted-momentum-v2"
    assert result.kospi.model_version == "코스피"
    assert result.price_momentum_v1.rebalance_count >= 2
    assert result.risk_adjusted_momentum_v2.average_turnover >= 0
    assert result.price_momentum_v1.metrics.observation_count > 0
    assert result.risk_adjusted_momentum_v2.metrics.cumulative_return > -1
    assert result.kospi.metrics.cumulative_return > -1
    assert result.price_momentum_v1.transaction_cost_bps == 10


def test_backtest_adjusts_a_validated_split_without_recording_a_50_percent_loss() -> None:
    stocks = stock_history()
    target = "S00024"
    target_rows = stocks.index[stocks["stock_code"].eq(target)]
    event_index = target_rows[220]
    stocks.loc[target_rows[220]:target_rows[-1], "listed_shares"] = 2_000_000
    stocks.loc[target_rows[220]:target_rows[-1], "close_price"] /= 2

    result = compare_momentum_strategies(stocks, benchmark(), config=CONFIG)

    assert result.price_momentum_v1.metrics.max_drawdown > -0.20
    assert result.risk_adjusted_momentum_v2.metrics.max_drawdown > -0.20


def test_backtest_fails_closed_on_an_ambiguous_share_and_price_discontinuity() -> None:
    stocks = stock_history()
    target_rows = stocks.index[stocks["stock_code"].eq("S00024")]
    stocks.loc[target_rows[220]:target_rows[-1], "listed_shares"] = 2_000_000
    stocks.loc[target_rows[220]:target_rows[-1], "close_price"] /= 4

    with pytest.raises(BacktestUnavailableError, match="corporate-action"):
        compare_momentum_strategies(stocks, benchmark(), config=CONFIG)


def test_transaction_cost_is_explicit_and_configurable() -> None:
    free = compare_momentum_strategies(stock_history(), benchmark(), config=CONFIG)
    costly = compare_momentum_strategies(
        stock_history(), benchmark(), config=CONFIG, transaction_cost_bps=25
    )

    assert costly.price_momentum_v1.metrics.cumulative_return < free.price_momentum_v1.metrics.cumulative_return
    assert costly.risk_adjusted_momentum_v2.metrics.cumulative_return < free.risk_adjusted_momentum_v2.metrics.cumulative_return


def test_portfolio_weights_drift_with_held_security_returns() -> None:
    net_return, closing_weights = _apply_daily_returns(
        {"winner": 0.475, "flat": 0.475},
        pd.Series({"winner": 0.50, "flat": 0.0}),
    )

    assert net_return == pytest.approx(0.2375)
    assert closing_weights["winner"] > 0.475
    assert closing_weights["winner"] > closing_weights["flat"]
    assert closing_weights["winner"] == pytest.approx(0.7125 / 1.2375)


def test_evaluation_start_keeps_warmup_history_but_delays_common_rebalancing() -> None:
    result = compare_momentum_strategies(
        stock_history(),
        benchmark(),
        config=CONFIG,
        evaluation_start="2025-10-01",
    )

    assert result.start_date >= "2025-10-01"


def test_evaluation_end_truncates_all_comparison_legs_equally() -> None:
    result = compare_momentum_strategies(
        stock_history(),
        benchmark(),
        config=CONFIG,
        evaluation_end="2025-10-31",
    )

    assert result.end_date <= "2025-10-31"
