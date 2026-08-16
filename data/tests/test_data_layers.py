import pandas as pd
import pytest
from datetime import date

from scripts.build_stock_price_features import compute_price_features, feature_path


def test_feature_path_is_versioned_and_month_partitioned() -> None:
    assert feature_path(month=date(2026, 8, 1), version="2") == (
        "stock_price/version=v2/year=2026/month=08/part-00000.parquet"
    )


def test_price_features_do_not_leak_rolling_values_across_stocks() -> None:
    dates = pd.date_range("2026-01-01", periods=21, freq="D")
    frame = pd.concat(
        [
            pd.DataFrame({"stock_code": "AAA", "trade_date": dates, "close_price": range(100, 121), "volume": range(1000, 1021)}),
            pd.DataFrame({"stock_code": "BBB", "trade_date": dates, "close_price": range(200, 221), "volume": range(2000, 2021)}),
        ],
        ignore_index=True,
    )
    result = compute_price_features(frame)
    aaa = result[result["stock_code"] == "AAA"].reset_index(drop=True)
    bbb = result[result["stock_code"] == "BBB"].reset_index(drop=True)
    assert pd.isna(aaa.loc[0, "return_1d"])
    assert pd.isna(bbb.loc[0, "return_1d"])
    assert pd.isna(aaa.loc[18, "sma_20"])
    assert pd.isna(bbb.loc[18, "sma_20"])
    assert aaa.loc[19, "sma_20"] == pytest.approx(109.5)
    assert bbb.loc[19, "sma_20"] == pytest.approx(209.5)
    assert aaa.loc[20, "momentum_20"] == pytest.approx(0.2)
    assert bbb.loc[20, "momentum_20"] == pytest.approx(0.1)
