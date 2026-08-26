import numpy as np
import pandas as pd
import pytest

from models.contracts import validate_feature_columns
from models.ml_rankers import LightGBMStockRanker, RankerConfig, RidgeStockRanker


def training_frame() -> pd.DataFrame:
    rows = []
    for day in range(1, 8):
        for stock in range(4):
            rows.append({
                "trade_date": f"2026-01-{day:02d}",
                "stock_code": f"{stock:06d}",
                "signal": float(stock + day),
                "target_return_20d": float(stock + day) / 100,
                "target_date_20d": f"2026-01-{min(day + 1, 8):02d}",
                "eligible_target_20d": True,
            })
    return pd.DataFrame(rows)


def test_target_columns_are_rejected_as_features() -> None:
    with pytest.raises(ValueError):
        validate_feature_columns(["signal", "target_return_20d"])


@pytest.mark.parametrize("ranker_type", [RidgeStockRanker, LightGBMStockRanker])
def test_ml_rankers_only_predict_after_training_cutoff(ranker_type) -> None:
    config = RankerConfig(feature_columns=("signal",))
    ranker = ranker_type(config).fit(training_frame(), training_end="2026-01-07")
    future = pd.DataFrame({
        "trade_date": ["2026-01-08"] * 3,
        "stock_code": ["A", "B", "C"],
        "signal": [1.0, 2.0, np.nan],
    })
    result = ranker.predict(future).frame
    assert sorted(result["rank"].tolist()) == [1, 2, 3]
    with pytest.raises(ValueError):
        ranker.predict(training_frame().iloc[:1])
