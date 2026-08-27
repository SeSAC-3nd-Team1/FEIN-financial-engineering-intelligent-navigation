"""Generate the Backend recommendation artifact from versioned Azure datasets."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
from typing import Iterable

import pandas as pd

from data_access import FeatureFile, FeatureStore, FeatureStoreConfig
from inference.recommendation_snapshot import (
    RecommendationSnapshot,
    export_recommendation_snapshot,
)
from risk import StockRiskConfig, apply_stock_risk_filter

MODEL_COLUMNS = (
    "stock_code",
    "trade_date",
    "close_price",
    "market_cap",
    "momentum_120d",
    "trading_value_sma_20d",
    "volatility_60d",
    "volume_ratio_20d",
    "history_120d_ready",
)
ALGORITHM_COLUMNS = ("symbol", "Date", "is_tradable")
SECURITY_MASTER_COLUMNS = ("reference_date", "stock_code", "stock_name")
DEFAULT_OUTPUT_PATH = Path("/model-artifacts/model_recommendation_snapshot.json")
RISK_FILTER_VERSION = "v1"


def _normalize_stock_codes(values: pd.Series) -> pd.Series:
    """Normalize KRX short codes from either `005930` or master-style `A005930`."""

    return (
        values.astype("string")
        .str.strip()
        .str.replace(r"^A(?=\d{6}$)", "", regex=True)
        .str.zfill(6)
    )


def data_lineage(
    model_version: str, algorithm_version: str, master_version: str
) -> str:
    """Describe every versioned input that affects the recommendation."""

    return (
        f"model_stock_daily-v{model_version.removeprefix('v')}+"
        f"algorithm_ohlcv-v{algorithm_version.removeprefix('v')}+"
        f"security_master_latest-v{master_version.removeprefix('v')}+"
        f"risk-filter-{RISK_FILTER_VERSION}"
    )


def _latest_partition_files(
    files: Iterable[FeatureFile], dataset: str
) -> tuple[FeatureFile, ...]:
    available = tuple(files)
    if not available:
        raise RuntimeError(f"Azure Feature dataset has no Parquet files: {dataset}")
    latest_partition = max(
        str(PurePosixPath(file.path).parent) for file in available
    )
    return tuple(
        file
        for file in available
        if str(PurePosixPath(file.path).parent) == latest_partition
    )


def _read_latest_partition(
    store: FeatureStore,
    dataset: str,
    version: str,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    files = _latest_partition_files(store.parquet_files(dataset, version), dataset)
    frames = [
        store.read_partition(file.path, columns=columns, etag=file.etag) for file in files
    ]
    return pd.concat(frames, ignore_index=True)


def _read_all_partitions(
    store: FeatureStore,
    dataset: str,
    version: str,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    files = tuple(store.parquet_files(dataset, version))
    if not files:
        raise RuntimeError(f"Azure Feature dataset has no Parquet files: {dataset}")
    return pd.concat(
        [
            store.read_partition(file.path, columns=columns, etag=file.etag)
            for file in files
        ],
        ignore_index=True,
    )


def build_latest_feature_frame(
    store: FeatureStore,
    *,
    model_version: str,
    algorithm_version: str,
    master_version: str,
    risk_config: StockRiskConfig = StockRiskConfig(),
) -> pd.DataFrame:
    """Load, align, and risk-filter the latest real Azure recommendation inputs."""

    model = _read_latest_partition(
        store, "model_stock_daily", model_version, MODEL_COLUMNS
    )
    algorithm = _read_latest_partition(
        store, "algorithm_ohlcv", algorithm_version, ALGORITHM_COLUMNS
    ).rename(columns={"symbol": "stock_code", "Date": "trade_date"})
    master = _read_all_partitions(
        store,
        "security_master_latest",
        master_version,
        SECURITY_MASTER_COLUMNS,
    )

    for frame in (model, algorithm):
        frame["stock_code"] = _normalize_stock_codes(frame["stock_code"])
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise")
        if frame[["stock_code", "trade_date"]].isna().any(axis=None):
            raise ValueError("Azure Feature join keys cannot be null")
        if frame.duplicated(["stock_code", "trade_date"]).any():
            raise ValueError("Azure Feature join keys must be unique")

    master["reference_date"] = pd.to_datetime(
        master["reference_date"], errors="raise"
    )
    master["stock_code"] = _normalize_stock_codes(master["stock_code"])
    master["stock_name"] = master["stock_name"].astype("string")
    master = (
        master.sort_values(["stock_code", "reference_date"])
        .drop_duplicates("stock_code", keep="last")
        .loc[:, ["stock_code", "stock_name"]]
    )

    model_latest = model["trade_date"].max()
    algorithm_latest = algorithm["trade_date"].max()
    if model_latest != algorithm_latest:
        raise ValueError(
            "latest Azure Feature dates do not match: "
            f"model_stock_daily={model_latest.date()}, "
            f"algorithm_ohlcv={algorithm_latest.date()}"
        )

    latest_model = model.loc[model["trade_date"].eq(model_latest)].copy()
    latest_algorithm = algorithm.loc[
        algorithm["trade_date"].eq(algorithm_latest),
        ["stock_code", "trade_date", "is_tradable"],
    ]
    combined = latest_model.merge(
        latest_algorithm,
        on=["stock_code", "trade_date"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    missing = combined.loc[combined["_merge"].ne("both"), "stock_code"]
    if not missing.empty:
        examples = ", ".join(missing.astype(str).head(5))
        raise ValueError(
            f"algorithm_ohlcv is missing {len(missing)} latest model rows; examples: {examples}"
        )
    combined = combined.merge(
        master,
        on="stock_code",
        how="left",
        validate="many_to_one",
    )
    return apply_stock_risk_filter(
        combined.drop(columns="_merge"), config=risk_config
    )


def generate_latest_recommendations(
    store: FeatureStore,
    output_path: str | Path,
    *,
    model_version: str,
    algorithm_version: str,
    master_version: str,
    market_regime: str = "neutral",
    top_n: int = 5,
    risk_config: StockRiskConfig = StockRiskConfig(),
) -> RecommendationSnapshot:
    """Run the complete Azure Feature -> risk -> model -> artifact path."""

    features = build_latest_feature_frame(
        store,
        model_version=model_version,
        algorithm_version=algorithm_version,
        master_version=master_version,
        risk_config=risk_config,
    )
    return export_recommendation_snapshot(
        features,
        output_path,
        data_version=data_lineage(model_version, algorithm_version, master_version),
        market_regime=market_regime,
        top_n=top_n,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the latest recommendation artifact from Azure Feature datasets."
        )
    )
    parser.add_argument("--model-version", default="2")
    parser.add_argument("--algorithm-version", default="2")
    parser.add_argument("--master-version", default="1")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            os.getenv("MODEL_RECOMMENDATION_SNAPSHOT_PATH", str(DEFAULT_OUTPUT_PATH))
        ),
    )
    parser.add_argument(
        "--market-regime",
        choices=("risk_on", "neutral", "risk_off"),
        default="neutral",
    )
    parser.add_argument("--top-n", type=int, default=5)
    return parser


def main() -> int:
    args = _parser().parse_args()
    snapshot = generate_latest_recommendations(
        FeatureStore(FeatureStoreConfig.from_env()),
        args.output,
        model_version=args.model_version,
        algorithm_version=args.algorithm_version,
        master_version=args.master_version,
        market_regime=args.market_regime,
        top_n=args.top_n,
    )
    print(
        f"exported {len(snapshot.recommendations)} recommendations "
        f"for {snapshot.as_of} ({snapshot.data_version}) to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
