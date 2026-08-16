"""Raw profile → Processed → 모델 Feature Dataset을 한 번에 실행한다."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

import features.model_dataset as model_dataset
from features.runtime_loader import load_processed_operation_compact
from processing.processed_builder import build_processed_dataset
from storage import BlobStorage

DATASETS = [
    "disclosure",
    "financial_statement",
    "market_index",
    "security_product",
    "stock_dividend",
    "stock_issuance",
    "stock_master",
    "stock_price",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path("reports/raw-profile"),
    )
    parser.add_argument("--dataset", action="append", choices=DATASETS)
    parser.add_argument("--schema-version", default="1")
    parser.add_argument("--feature-version", default="1")
    parser.add_argument("--skip-processed", action="store_true")
    parser.add_argument("--skip-features", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)

    storage = BlobStorage.from_env()
    raw_container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    processed_container = os.getenv(
        "AZURE_STORAGE_CONTAINER_PROCESSED",
        "processed",
    )
    features_container = os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features")
    selected = args.dataset or DATASETS

    summaries = []
    if not args.skip_processed:
        for dataset in selected:
            profile_path = args.profile_dir / f"{dataset}.json"
            if not profile_path.is_file():
                raise FileNotFoundError(f"profile report not found: {profile_path}")
            summaries.append(
                build_processed_dataset(
                    storage,
                    raw_container=raw_container,
                    processed_container=processed_container,
                    dataset=dataset,
                    profile=json.loads(profile_path.read_text(encoding="utf-8")),
                    schema_version=args.schema_version,
                    overwrite=args.overwrite,
                )
            )
        print("PROCESSED COMPLETE " + json.dumps(summaries, ensure_ascii=False))

    if not args.skip_features:
        # Processed의 row-level lineage는 저장소에 이미 보존되어 있다. 모델 계산에서는 제거해
        # 수백만 행 문자열이 차지하는 메모리를 줄이고 Dataset manifest로 lineage를 추적한다.
        model_dataset.load_processed_operation = load_processed_operation_compact
        result = model_dataset.build_model_datasets(
            storage,
            processed_container=processed_container,
            features_container=features_container,
            schema_version=args.schema_version,
            feature_version=args.feature_version,
            overwrite=args.overwrite,
        )
        print("FEATURE DATASETS COMPLETE " + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
