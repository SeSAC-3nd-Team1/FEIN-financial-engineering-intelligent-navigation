"""Verify legacy Raw migration blobs against canonical YYYY/MM outputs.

For every source migration blob this script rebuilds the exact monthly groups,
recomputes their deterministic destination paths and gzip payloads, and checks
that the corresponding canonical blobs exist byte-for-byte. Source blobs are
read-only; this verifier never creates, overwrites, or deletes Blob objects.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import date
from typing import Any

from scripts.repartition_existing_raw_blobs import record_partition_month
from storage.blob import BlobStorage
from storage.paths import build_raw_path
from storage.raw import serialize_jsonl_gzip


EXPECTED_DATASET_COUNTS = {
    "disclosure": 80_045,
    "financial_statement": 1_239_611,
    "market_index": 467_358,
    "security_product": 5_362_704,
    "stock_dividend": 71_681,
    "stock_issuance": 10_135_621,
    "stock_master": 3_211_333,
    "stock_price": 3_502_426,
}
EXPECTED_TOTAL_RECORDS = 24_070_779
EXPECTED_SOURCE_BLOBS = 525
_MONTHLY_PATH = re.compile(r"/year=(\d{4})/month=(\d{2})/([^/]+\.jsonl\.gz)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Raw YYYY/MM repartition integrity.")
    parser.add_argument("--dataset", choices=sorted(EXPECTED_DATASET_COUNTS))
    parser.add_argument(
        "--audit-layout",
        action="store_true",
        help="Audit source blob count and report canonical monthly/day layouts.",
    )
    return parser.parse_args()


def _decode_jsonl_gzip(data: bytes) -> list[dict[str, Any]]:
    payload = gzip.decompress(data)
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _source_paths(storage: BlobStorage, container: str, dataset: str) -> list[str]:
    prefix = f"migration/data-go-kr/{dataset}/"
    return sorted(
        path
        for path in storage.list_paths(container, prefix=prefix)
        if path.endswith(".jsonl.gz")
    )


def verify_dataset(storage: BlobStorage, container: str, dataset: str) -> None:
    source_paths = _source_paths(storage, container, dataset)
    if not source_paths:
        raise RuntimeError(f"No migration source blobs found for {dataset}")

    expected_paths: set[str] = set()
    source_records = 0
    verified_records = 0
    verified_blobs = 0

    for source_index, source_path in enumerate(source_paths, start=1):
        source_data = storage.download_bytes(container, source_path)
        records = _decode_jsonl_gzip(source_data)
        grouped: dict[tuple[str, str, date], list[dict[str, Any]]] = defaultdict(list)

        for record in records:
            record_dataset = str(record.get("dataset") or "").strip()
            operation = str(record.get("operation") or "").strip()
            if record_dataset.lower() != dataset.lower():
                raise RuntimeError(
                    f"Dataset mismatch source={source_path} record={record_dataset!r}"
                )
            if not operation:
                raise RuntimeError(f"Missing operation in {source_path}")
            month = record_partition_month(record)
            grouped[(record_dataset, operation, month)].append(record)

        if sum(len(items) for items in grouped.values()) != len(records):
            raise RuntimeError(f"Grouping count mismatch for {source_path}")

        for (record_dataset, operation, month), monthly_records in sorted(grouped.items()):
            if any(record_partition_month(record) != month for record in monthly_records):
                raise RuntimeError(
                    f"Source month boundary violation: {record_dataset}/{operation}/{month:%Y-%m}"
                )

            expected_batch = serialize_jsonl_gzip(monthly_records)
            destination_path = build_raw_path(
                source="data-go-kr",
                dataset=record_dataset,
                operation=operation,
                partition_date=month,
                batch_hash=expected_batch.batch_hash,
                page_number=None,
                migration=False,
                monthly_partition=True,
            )

            if destination_path in expected_paths:
                raise RuntimeError(
                    "Duplicate destination path derived from different migration groups: "
                    f"{destination_path}"
                )
            expected_paths.add(destination_path)

            match = _MONTHLY_PATH.search(destination_path)
            if not match or "/day=" in destination_path:
                raise RuntimeError(f"Destination is not YYYY/MM-only: {destination_path}")
            if int(match.group(1)) != month.year or int(match.group(2)) != month.month:
                raise RuntimeError(f"Destination partition mismatch: {destination_path}")

            if not storage.exists(container, destination_path):
                raise RuntimeError(f"Missing canonical blob: {destination_path}")

            props = storage.properties(container, destination_path)
            metadata = props.metadata
            if int(metadata.get("record_count", "-1")) != len(monthly_records):
                raise RuntimeError(f"record_count metadata mismatch: {destination_path}")
            if metadata.get("batch_hash") != expected_batch.batch_hash:
                raise RuntimeError(f"batch_hash metadata mismatch: {destination_path}")
            if metadata.get("content_sha256") != expected_batch.content_sha256:
                raise RuntimeError(f"content_sha256 metadata mismatch: {destination_path}")

            destination_data = storage.download_bytes(container, destination_path)
            actual_content_sha256 = hashlib.sha256(destination_data).hexdigest()
            if actual_content_sha256 != expected_batch.content_sha256:
                raise RuntimeError(f"Blob byte hash mismatch: {destination_path}")

            destination_records = _decode_jsonl_gzip(destination_data)
            if destination_records != monthly_records:
                raise RuntimeError(f"Record content/order mismatch: {destination_path}")
            if any(record_partition_month(record) != month for record in destination_records):
                raise RuntimeError(f"Canonical blob spans months: {destination_path}")

            verified_records += len(destination_records)
            verified_blobs += 1

        source_records += len(records)
        print(
            f"VERIFY SOURCE {source_index}/{len(source_paths)} "
            f"rows={len(records)} groups={len(grouped)} path={source_path}"
        )

    expected_records = EXPECTED_DATASET_COUNTS[dataset]
    if source_records != expected_records:
        raise RuntimeError(
            f"Unexpected source count for {dataset}: "
            f"expected={expected_records} actual={source_records}"
        )
    if verified_records != source_records:
        raise RuntimeError(
            f"Verified record mismatch for {dataset}: "
            f"source={source_records} verified={verified_records}"
        )

    print(
        f"VERIFY DATASET COMPLETE dataset={dataset} source_blobs={len(source_paths)} "
        f"canonical_blobs={verified_blobs} records={verified_records}"
    )


def audit_layout(storage: BlobStorage, container: str) -> None:
    source_paths = [
        path
        for path in storage.list_paths(container, prefix="migration/data-go-kr/")
        if path.endswith(".jsonl.gz")
    ]
    if len(source_paths) != EXPECTED_SOURCE_BLOBS:
        raise RuntimeError(
            f"Unexpected migration source blob count: "
            f"expected={EXPECTED_SOURCE_BLOBS} actual={len(source_paths)}"
        )

    canonical_paths = [
        path
        for path in storage.list_paths(container, prefix="data-go-kr/")
        if path.endswith(".jsonl.gz")
    ]
    monthly_paths = [path for path in canonical_paths if _MONTHLY_PATH.search(path)]
    day_paths = [path for path in canonical_paths if "/day=" in path]
    other_paths = [
        path for path in canonical_paths if path not in monthly_paths and path not in day_paths
    ]

    print(
        f"LAYOUT AUDIT migration_source_blobs={len(source_paths)} "
        f"canonical_blobs={len(canonical_paths)} monthly_blobs={len(monthly_paths)} "
        f"legacy_day_blobs={len(day_paths)} other_blobs={len(other_paths)}"
    )
    for path in day_paths:
        print(f"LAYOUT WARNING legacy_day_blob={path}")
    for path in other_paths:
        print(f"LAYOUT WARNING non_monthly_blob={path}")


def main() -> None:
    args = parse_args()
    if not args.dataset and not args.audit_layout:
        raise ValueError("Specify --dataset and/or --audit-layout")

    if sum(EXPECTED_DATASET_COUNTS.values()) != EXPECTED_TOTAL_RECORDS:
        raise RuntimeError("Expected dataset counts do not add up to expected total")

    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")

    if args.dataset:
        verify_dataset(storage, container, args.dataset)
    if args.audit_layout:
        audit_layout(storage, container)


if __name__ == "__main__":
    main()
