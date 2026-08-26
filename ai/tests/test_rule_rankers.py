import pandas as pd

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
