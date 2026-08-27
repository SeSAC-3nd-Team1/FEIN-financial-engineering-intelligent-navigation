import json
from pathlib import Path

import pandas as pd
import pytest

from data_access import FeatureFile
from inference.generate_latest_recommendations import (
    build_latest_feature_frame,
    data_lineage,
    generate_latest_recommendations,
)


class FakeFeatureStore:
    def __init__(self, model: pd.DataFrame, algorithm: pd.DataFrame) -> None:
        self.frames = {
            "model_stock_daily": model,
            "algorithm_ohlcv": algorithm,
        }

    def parquet_files(self, dataset: str, version: str) -> tuple[FeatureFile, ...]:
        return (
            FeatureFile(
                path=f"{dataset}/version=v{version}/year=2026/month=07/part.parquet",
                size=1,
                etag=f"{dataset}-old-etag",
            ),
            FeatureFile(
                path=f"{dataset}/version=v{version}/year=2026/month=08/part.parquet",
                size=1,
                etag=f"{dataset}-etag",
            ),
        )

    def read_partition(
        self, path: str, columns: tuple[str, ...], *, etag: str | None = None
    ) -> pd.DataFrame:
        dataset = path.split("/", 1)[0]
        assert "month=08" in path
        assert etag == f"{dataset}-etag"
        return self.frames[dataset].loc[:, list(columns)].copy()


def model_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "stock_code": ["005930", "000660"],
            "trade_date": ["2026-08-26"] * 2,
            "close_price": [70_000, 250_000],
            "market_cap": [400, 300],
            "momentum_120d": [0.2, 0.4],
            "trading_value_sma_20d": [100, 100],
            "volatility_60d": [0.2, 0.3],
            "volume_ratio_20d": [1.0, 1.2],
            "history_120d_ready": [True, True],
        }
    )


def algorithm_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["005930", "000660"],
            "Date": ["2026-08-26"] * 2,
            "is_tradable": [True, True],
        }
    )


def test_real_dataset_pipeline_joins_filters_and_exports(tmp_path: Path) -> None:
    output = tmp_path / "snapshot.json"
    store = FakeFeatureStore(model_frame(), algorithm_frame())

    snapshot = generate_latest_recommendations(
        store,  # type: ignore[arg-type]
        output,
        model_version="2",
        algorithm_version="v2",
        top_n=2,
    )

    assert snapshot.data_version == (
        "model_stock_daily-v2+algorithm_ohlcv-v2+risk-filter-v1"
    )
    assert [item.symbol for item in snapshot.recommendations] == ["000660", "005930"]
    assert json.loads(output.read_text(encoding="utf-8"))["as_of"] == "2026-08-26"


def test_pipeline_rejects_misaligned_latest_dates() -> None:
    algorithm = algorithm_frame()
    algorithm["Date"] = "2026-08-25"

    with pytest.raises(ValueError, match="latest Azure Feature dates do not match"):
        build_latest_feature_frame(
            FakeFeatureStore(model_frame(), algorithm),  # type: ignore[arg-type]
            model_version="2",
            algorithm_version="2",
        )


def test_pipeline_rejects_missing_algorithm_rows() -> None:
    with pytest.raises(ValueError, match="missing 1 latest model rows"):
        build_latest_feature_frame(
            FakeFeatureStore(model_frame(), algorithm_frame().iloc[:1]),  # type: ignore[arg-type]
            model_version="2",
            algorithm_version="2",
        )


def test_pipeline_computes_risk_eligibility() -> None:
    model = model_frame()
    model.loc[model["stock_code"].eq("000660"), "volatility_60d"] = 1.2

    features = build_latest_feature_frame(
        FakeFeatureStore(model, algorithm_frame()),  # type: ignore[arg-type]
        model_version="2",
        algorithm_version="2",
    ).set_index("stock_code")

    assert bool(features.loc["005930", "risk_eligible"])
    assert not bool(features.loc["000660", "risk_eligible"])
    assert features.loc["000660", "risk_reason"] == "volatility"


def test_data_lineage_normalizes_version_prefixes() -> None:
    assert data_lineage("v3", "4") == (
        "model_stock_daily-v3+algorithm_ohlcv-v4+risk-filter-v1"
    )
