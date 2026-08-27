"""CLI that publishes a model-generated recommendation artifact for the Backend."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from inference.recommendation_snapshot import export_recommendation_snapshot


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and atomically export the latest price-model recommendation snapshot."
    )
    parser.add_argument("--input", required=True, type=Path, help="Feature CSV or Parquet path")
    parser.add_argument("--output", required=True, type=Path, help="Snapshot JSON artifact path")
    parser.add_argument("--data-version", required=True)
    parser.add_argument(
        "--market-regime",
        choices=("risk_on", "neutral", "risk_off"),
        default="neutral",
    )
    parser.add_argument("--top-n", type=int, default=5)
    return parser


def _read_features(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, dtype={"stock_code": "string"})
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError("input must be a CSV or Parquet file")


def main() -> int:
    args = _parser().parse_args()
    snapshot = export_recommendation_snapshot(
        _read_features(args.input),
        args.output,
        data_version=args.data_version,
        market_regime=args.market_regime,
        top_n=args.top_n,
    )
    print(
        f"exported {len(snapshot.recommendations)} recommendations "
        f"for {snapshot.as_of} to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
