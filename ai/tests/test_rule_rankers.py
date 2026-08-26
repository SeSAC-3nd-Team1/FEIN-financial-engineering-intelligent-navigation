import pandas as pd
import pytest

from models.rule_rankers import LowVolatilityRanker, MomentumRanker, RuleSelectionConfig


def panel() -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": ["2026-01-02"] * 4,
        "stock_code": ["A", "B", "C", "D"],
        "market_cap": [400, 300, 200, 100],
        "trading_value_sma_20d": [10, 10, 10, 10],
        "volatility_60d": [0.30, 0.10, 0.20, 0.05],
        "momentum_120d": [0.05, 0.10, -0.10, 0.50],
    })


def test_low_volatility_uses_point_in_time_market_cap_universe() -> None:
    ranked = LowVolatilityRanker(RuleSelectionConfig(top_n=1, universe_size=3)).rank(panel())
    assert ranked.loc[ranked["selected"], "stock_code"].tolist() == ["B"]
    assert "D" not in ranked["stock_code"].tolist()


def test_momentum_selects_highest_return() -> None:
    ranked = MomentumRanker(RuleSelectionConfig(top_n=2, universe_size=4)).rank(panel())
    assert ranked.loc[ranked["selected"], "stock_code"].tolist() == ["D", "B"]


def test_liquidity_filter_requires_trading_value_column() -> None:
    frame = panel().drop(columns="trading_value_sma_20d")
    config = RuleSelectionConfig(top_n=1, universe_size=3, min_trading_value=1.0)

    with pytest.raises(ValueError, match="trading_value_sma_20d"):
        MomentumRanker(config).rank(frame)


@pytest.mark.parametrize("invalid_key", [None, "duplicate"])
def test_rule_ranker_rejects_invalid_point_in_time_keys(invalid_key: str | None) -> None:
    frame = panel()
    if invalid_key is None:
        frame.loc[0, "stock_code"] = None
    else:
        frame.loc[1, "stock_code"] = frame.loc[0, "stock_code"]

    with pytest.raises(ValueError):
        MomentumRanker(RuleSelectionConfig(top_n=2, universe_size=4)).rank(frame)
