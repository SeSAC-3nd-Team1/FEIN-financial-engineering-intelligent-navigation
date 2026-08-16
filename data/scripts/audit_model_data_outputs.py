"""Azure Processed/Features 산출물의 객체 수·레코드 수·품질 manifest를 감사한다."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from storage import BlobStorage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--schema-version", default="1")
    parser.add_argument("--feature-version", default="1")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _int_metadata(metadata: dict[str, str] | None, key: str) -> int:
    if not metadata or key not in metadata:
        return 0
    return int(metadata[key])


def audit_processed(
    storage: BlobStorage,
    container: str,
    schema_version: str,
) -> dict[str, Any]:
    client = storage.service_client.get_container_client(container)
    by_dataset: dict[str, dict[str, int]] = defaultdict(
        lambda: {"objects": 0, "records": 0, "bytes": 0}
    )
    quality = {
        "manifests": 0,
        "accepted": 0,
        "rejected": 0,
        "conversion_errors": defaultdict(int),
        "reasons": defaultdict(int),
    }

    schema_marker = f"/schema=v{schema_version}/"
    for blob in client.list_blobs(include=["metadata"]):
        name = str(blob.name)
        if name.startswith("_quality/") and name.endswith("manifest.json"):
            if schema_marker not in name:
                continue
            manifest = json.loads(storage.download_bytes(container, name))
            quality["manifests"] += 1
            quality["accepted"] += int(manifest.get("accepted", 0))
            quality["rejected"] += int(manifest.get("rejected", 0))
            for key, value in manifest.get("conversion_errors", {}).items():
                quality["conversion_errors"][key] += int(value)
            for key, value in manifest.get("reasons", {}).items():
                quality["reasons"][key] += int(value)
            continue

        if not name.endswith(".parquet") or schema_marker not in name:
            continue
        dataset = name.split("/", 1)[0]
        group = by_dataset[dataset]
        group["objects"] += 1
        group["records"] += _int_metadata(blob.metadata, "record_count")
        group["bytes"] += int(blob.size or 0)

    return {
        "datasets": dict(sorted(by_dataset.items())),
        "total_objects": sum(item["objects"] for item in by_dataset.values()),
        "total_records": sum(item["records"] for item in by_dataset.values()),
        "total_bytes": sum(item["bytes"] for item in by_dataset.values()),
        "quality": {
            "manifests": quality["manifests"],
            "accepted": quality["accepted"],
            "rejected": quality["rejected"],
            "conversion_errors": dict(sorted(quality["conversion_errors"].items())),
            "reasons": dict(sorted(quality["reasons"].items())),
        },
    }


def audit_features(
    storage: BlobStorage,
    container: str,
    feature_version: str,
) -> dict[str, Any]:
    client = storage.service_client.get_container_client(container)
    marker = f"/version=v{feature_version}/"
    by_dataset: dict[str, dict[str, int]] = defaultdict(
        lambda: {"objects": 0, "records": 0, "bytes": 0}
    )

    for blob in client.list_blobs(include=["metadata"]):
        name = str(blob.name)
        if not name.endswith(".parquet") or marker not in name:
            continue
        dataset = name.split("/", 1)[0]
        group = by_dataset[dataset]
        group["objects"] += 1
        group["records"] += _int_metadata(blob.metadata, "record_count")
        group["bytes"] += int(blob.size or 0)

    manifest_path = (
        f"_manifests/model-datasets/version=v{feature_version}/manifest.json"
    )
    manifest = json.loads(storage.download_bytes(container, manifest_path))
    return {
        "datasets": dict(sorted(by_dataset.items())),
        "total_objects": sum(item["objects"] for item in by_dataset.values()),
        "total_records": sum(item["records"] for item in by_dataset.values()),
        "total_bytes": sum(item["bytes"] for item in by_dataset.values()),
        "manifest_path": manifest_path,
        "manifest": manifest,
    }


def main() -> None:
    args = parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)

    storage = BlobStorage.from_env()
    payload = {
        "processed": audit_processed(
            storage,
            os.getenv("AZURE_STORAGE_CONTAINER_PROCESSED", "processed"),
            args.schema_version,
        ),
        "features": audit_features(
            storage,
            os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features"),
            args.feature_version,
        ),
    }

    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
