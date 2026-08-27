"""Validate one Azure Feature Dataset version and write its training manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from data_access import FeatureStore, FeatureStoreConfig


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a versioned Azure Feature Dataset before training"
    )
    parser.add_argument(
        "--dataset",
        choices=("model_stock_daily",),
        default="model_stock_daily",
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    store = FeatureStore(FeatureStoreConfig.from_env())
    manifest = store.build_training_manifest(args.dataset, args.version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(manifest.to_json() + "\n", encoding="utf-8")
    print(
        "FEATURE DATASET VALID "
        f"dataset={manifest.dataset} version=v{manifest.version} "
        f"rows={manifest.report.row_count} manifest_id={manifest.manifest_id} "
        f"output={args.output}"
    )


if __name__ == "__main__":
    main()
