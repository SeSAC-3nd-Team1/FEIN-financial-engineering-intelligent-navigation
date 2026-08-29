"""Generate risk-adjusted-momentum-v2 from real versioned Azure Features."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

from inference.risk_adjusted_recommendation_snapshot import (
    export_risk_adjusted_recommendation_snapshot,
)
from models.risk_adjusted_momentum import RiskAdjustedMomentumConfig
from risk import StockRiskConfig, apply_stock_risk_filter

MODEL_COLUMNS = (
    "stock_code",
    "trade_date",
    "close_price",
    "listed_shares",
    "market_cap",
    "momentum_120d",
    "trading_value_sma_20d",
    "volatility_60d",
    "volume_ratio_20d",
    "history_120d_ready",
)
ALGORITHM_COLUMNS = ("symbol", "Date", "is_tradable")
SECURITY_MASTER_COLUMNS = ("reference_date", "stock_code", "stock_name")
DEFAULT_OUTPUT_PATH = Path("/model-artifacts/risk-adjusted-momentum-v2.json")
RISK_FILTER_VERSION = "v1"


def v2_data_lineage(model_version: str, algorithm_version: str, master_version: str) -> str:
    """Record every Azure input and the explicit no-short-rate policy."""

    return (
        f"model-v{model_version.removeprefix('v')}+"
        f"algo-v{algorithm_version.removeprefix('v')}+"
        f"master-v{master_version.removeprefix('v')}+"
        f"risk-{RISK_FILTER_VERSION}+ca-pit-v1+rf-neutral"
    )


def build_v2_feature_history(
    store: FeatureStore,
    *,
    model_version: str,
    algorithm_version: str,
    master_version: str,
    risk_config: StockRiskConfig = StockRiskConfig(),
) -> pd.DataFrame:
    """Load full history because v2 requires 13-month momentum and 3-year volatility."""

    from data_access import FeatureStore, FeatureStoreConfig
    from inference.generate_latest_recommendations import _read_all_partitions

    model = _read_all_partitions(store, "model_stock_daily", model_version, MODEL_COLUMNS)
    algorithm = _read_all_partitions(
        store, "algorithm_ohlcv", algorithm_version, ALGORITHM_COLUMNS
    ).rename(columns={"symbol": "stock_code", "Date": "trade_date"})
    master = _read_all_partitions(
        store, "security_master_latest", master_version, SECURITY_MASTER_COLUMNS
    )
    return build_v2_feature_history_from_frames(model, algorithm, master, risk_config=risk_config)


def build_v2_feature_history_from_frames(
    model: pd.DataFrame,
    algorithm: pd.DataFrame,
    master: pd.DataFrame,
    *,
    risk_config: StockRiskConfig = StockRiskConfig(),
) -> pd.DataFrame:
    """Run the production Live merge/risk path against in-memory frames."""
    model = model.copy()
    algorithm = algorithm.copy()
    master = master.copy()
    def normalize(values: pd.Series) -> pd.Series:
        return values.astype("string").str.strip().str.replace(
            r"^A(?=\d{6}$)", "", regex=True
        ).str.zfill(6)

    for frame in (model, algorithm):
        frame["stock_code"] = normalize(frame["stock_code"])
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise")
        if frame[["stock_code", "trade_date"]].isna().any(axis=None):
            raise ValueError("Azure Feature join keys cannot be null")
        if frame.duplicated(["stock_code", "trade_date"]).any():
            raise ValueError("Azure Feature join keys must be unique")

    combined = model.merge(
        algorithm[["stock_code", "trade_date", "is_tradable"]],
        on=["stock_code", "trade_date"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    missing = combined.loc[combined["_merge"].ne("both"), "stock_code"]
    if not missing.empty:
        examples = ", ".join(missing.astype(str).head(5))
        raise ValueError(
            f"algorithm_ohlcv is missing {len(missing)} historical model rows; examples: {examples}"
        )

    master["reference_date"] = pd.to_datetime(master["reference_date"], errors="raise")
    master["stock_code"] = normalize(master["stock_code"])
    master = (
        master.sort_values(["stock_code", "reference_date"])
        .drop_duplicates("stock_code", keep="last")
        [["stock_code", "stock_name"]]
    )
    # latest master는 표시 이름에만 쓰며 역사적 universe/selection에는 사용하지 않는다.
    combined = combined.drop(columns="_merge").merge(
        master, on="stock_code", how="left", validate="many_to_one"
    )
    return apply_stock_risk_filter(combined, config=risk_config)


def generate_risk_adjusted_momentum(
    store: FeatureStore,
    output_path: str | Path,
    *,
    model_version: str,
    algorithm_version: str,
    master_version: str,
    market_regime: str = "neutral",
    risk_config: StockRiskConfig = StockRiskConfig(),
    model_config: RiskAdjustedMomentumConfig = RiskAdjustedMomentumConfig(),
):
    history = build_v2_feature_history(
        store,
        model_version=model_version,
        algorithm_version=algorithm_version,
        master_version=master_version,
        risk_config=risk_config,
    )
    return export_risk_adjusted_recommendation_snapshot(
        history,
        output_path,
        data_version=v2_data_lineage(model_version, algorithm_version, master_version),
        market_regime=market_regime,
        config=model_config,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate risk-adjusted-momentum-v2 from Azure Feature datasets."
    )
    parser.add_argument("--model-version", default="2")
    parser.add_argument("--algorithm-version", default="2")
    parser.add_argument("--master-version", default="1")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.getenv("RISK_ADJUSTED_MOMENTUM_V2_OUTPUT_PATH", str(DEFAULT_OUTPUT_PATH))),
    )
    parser.add_argument(
        "--market-regime", choices=("risk_on", "neutral", "risk_off"), default="neutral"
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    snapshot = generate_risk_adjusted_momentum(
        FeatureStore(FeatureStoreConfig.from_env()),
        args.output,
        model_version=args.model_version,
        algorithm_version=args.algorithm_version,
        master_version=args.master_version,
        market_regime=args.market_regime,
    )
    print(
        f"exported {len(snapshot.recommendations)} recommendations "
        f"for {snapshot.as_of} ({snapshot.data_version}) to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
