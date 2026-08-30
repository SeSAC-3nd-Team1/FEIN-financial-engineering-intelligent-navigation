"""Regression contract for the shared live/backtest Momentum feature source."""

import numpy as np
import pandas as pd
import pytest

from features.model_dataset import compute_stock_features
from shared.momentum_features import add_momentum_features


def _fixture() -> pd.DataFrame:
    rows = 121
    close = np.full(rows, 100.0)
    close[60] = np.nan  # intermediate gap must not change shift semantics
    return pd.DataFrame(
        {
            "stock_code": ["AAA"] * rows,
            "trade_date": pd.date_range("2025-01-01", periods=rows, freq="D"),
            "open_price": [100.0] * rows,
            "high_price": [101.0] * rows,
            "low_price": [99.0] * rows,
            "close_price": close,
            "volume": [0.0] * rows,
            "trading_value": [None] * rows,
        }
    )


def test_live_and_backtest_feature_contracts_match_on_edge_fixture() -> None:
    source = _fixture()
    live = add_momentum_features(source)
    backtest = compute_stock_features(source)

    for column in (
        "is_tradable",
        "history_120d_ready",
        "trading_value_sma_20d",
        "volatility_60d",
        "volume_ratio_20d",
    ):
        if column in ("trading_value_sma_20d", "volatility_60d", "volume_ratio_20d"):
            pd.testing.assert_series_equal(
                live[column], backtest[column], check_names=False, check_exact=False, rtol=1e-12, atol=1e-12
            )
        else:
            pd.testing.assert_series_equal(live[column], backtest[column], check_names=False)

    assert bool(live.iloc[-1]["history_120d_ready"]) is True
    assert bool(live.iloc[-1]["is_tradable"]) is True
    assert pd.isna(live.iloc[-1]["trading_value_sma_20d"])


@pytest.mark.parametrize(
    ("field", "value"),
    [("volume", -1.0), ("open_price", 0.0), ("high_price", 98.0)],
)
def test_live_and_backtest_quality_flags_match(field: str, value: float) -> None:
    source = _fixture()
    source.loc[120, field] = value

    live = add_momentum_features(source)
    backtest = compute_stock_features(source)

    assert bool(live.loc[120, "is_tradable"]) is False
    assert bool(backtest.loc[120, "is_tradable"]) is False
