from datetime import date, timedelta
from decimal import Decimal

import pytest

from scripts.demo_history import simulate_history
from scripts.seed_demo_account import TARGET_WEIGHTS, ensure_demo_environment


def market(days: int = 253):
    dates = [date(2025, 8, 1) + timedelta(days=index) for index in range(days)]
    closes = {
        "AAA": {
            day: Decimal("100") + Decimal(index) / Decimal("10")
            for index, day in enumerate(dates)
        },
        "BBB": {
            day: Decimal("200") - Decimal(index) / Decimal("20")
            for index, day in enumerate(dates)
        },
    }
    return dates, closes


def test_simulation_builds_one_year_of_consistent_snapshots_and_rebalances() -> None:
    dates, closes = market()
    result = simulate_history(
        dates,
        closes,
        {"AAA": Decimal("0.60"), "BBB": Decimal("0.35")},
        initial_cash=Decimal("3000000"),
    )

    assert len(result.snapshots) == 253
    assert result.snapshots[0].total_assets == Decimal("3000000.00")
    assert {trade.reason for trade in result.trades} == {
        "INITIAL_ALLOCATION",
        "MONTHLY_REBALANCE",
    }
    assert {
        trade.trade_date
        for trade in result.trades
        if trade.reason == "MONTHLY_REBALANCE"
    } == {dates[index] for index in range(21, 253, 21)}
    latest = result.snapshots[-1]
    assert latest.total_assets == latest.cash_balance + latest.total_evaluation_amount
    assert latest.unrealized_profit == (
        latest.total_evaluation_amount - latest.total_purchase_amount
    )
    assert result.final_cash == latest.cash_balance
    assert all(holding.quantity >= 0 for holding in result.holdings.values())


def test_simulation_rejects_missing_market_date() -> None:
    dates, closes = market(2)
    del closes["AAA"][dates[-1]]

    with pytest.raises(ValueError, match="종가가 없는 거래일"):
        simulate_history(
            dates,
            closes,
            {"AAA": Decimal("0.95")},
            initial_cash=Decimal("3000000"),
        )


def test_simulation_rotates_into_new_momentum_stocks() -> None:
    dates, closes = market(43)
    closes["CCC"] = {day: Decimal("300") for day in dates}
    result = simulate_history(
        dates,
        closes,
        {"AAA": Decimal("0.95")},
        initial_cash=Decimal("3000000"),
        target_weight_schedule={
            21: {"BBB": Decimal("0.45"), "CCC": Decimal("0.50")}
        },
    )

    rotation_trades = [trade for trade in result.trades if trade.trade_date == dates[21]]
    assert any(trade.stock_code == "AAA" and trade.side == "SELL" for trade in rotation_trades)
    assert any(trade.stock_code == "BBB" and trade.side == "BUY" for trade in rotation_trades)
    assert any(trade.stock_code == "CCC" and trade.side == "BUY" for trade in rotation_trades)
    assert result.holdings["AAA"].quantity == 0
    assert result.holdings["BBB"].quantity > 0
    assert result.holdings["CCC"].quantity > 0


def test_demo_seed_requires_explicit_opt_in_and_rejects_production() -> None:
    with pytest.raises(RuntimeError, match="DEMO_SEED_ENABLED"):
        ensure_demo_environment("", "development")
    with pytest.raises(RuntimeError, match="운영 환경"):
        ensure_demo_environment("true", "production")

    ensure_demo_environment("true", "demo")


def test_momentum_demo_keeps_five_percent_cash_target() -> None:
    assert len(TARGET_WEIGHTS) == 6
    assert sum(TARGET_WEIGHTS.values(), Decimal("0")) == Decimal("0.95")
    assert TARGET_WEIGHTS["005930"] == Decimal("0.20")
    assert TARGET_WEIGHTS["000660"] == Decimal("0.20")
