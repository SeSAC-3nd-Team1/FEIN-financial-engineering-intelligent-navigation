"""Repartition existing legacy Raw blobs into canonical YYYY/MM paths.

This script does not call external data APIs and does not delete source blobs.
It reads existing `migration/` JSONL+gzip blobs, keeps each decoded Raw record
unchanged, groups records by their semantic month, and writes content-addressed
monthly blobs under the canonical Raw prefix.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from storage.blob import BlobStorage
from storage.raw import RawBlobWriter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repartition existing Azure Raw blobs by each record's YYYY-MM."
    )
    parser.add_argument(
        "--source-prefix",
        default="migration/data-go-kr/",
        help="Existing Raw blob prefix to read; source blobs are never deleted.",
    )
    parser.add_argument("--dataset", help="Optional dataset filter.")
    parser.add_argument("--operation", help="Optional operation filter.")
    parser.add_argument(
        "--max-source-blobs",
        type=int,
        help="Safety limit for smoke tests; omit to process every matching source blob.",
    )
    return parser.parse_args()


def _parse_record_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return date.fromisoformat(text[:10])
    if len(text) >= 8 and text[:8].isdigit():
        return datetime.strptime(text[:8], "%Y%m%d").date()
    return None


def record_partition_month(record: dict[str, Any]) -> date:
    """Resolve the semantic month while leaving the record itself untouched."""

    legacy = record.get("legacy") or {}
    payload = record.get("payload") or {}
    resolved = (
        _parse_record_date(legacy.get("referenceDate"))
        or _parse_record_date(payload.get("basDt"))
        or _parse_record_date(record.get("collectedAt"))
    )
    if resolved is None:
        raise ValueError("Raw record has no usable referenceDate/basDt/collectedAt")
    return date(resolved.year, resolved.month, 1)


def _decode_jsonl_gzip(data: bytes) -> list[dict[str, Any]]:
    payload = gzip.decompress(data)
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _matches(path: str, *, dataset: str | None, operation: str | None) -> bool:
    if not path.endswith(".jsonl.gz"):
        return False
    if dataset and f"/{dataset.lower()}/" not in path.lower():
        return False
    if operation and f"operation={operation.lower()}/" not in path.lower():
        return False
    return True


def main() -> None:
    args = parse_args()
    if args.max_source_blobs is not None and args.max_source_blobs < 1:
        raise ValueError("--max-source-blobs must be at least 1")

    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    writer = RawBlobWriter(storage, container=container)

    paths = [
        path
        for path in storage.list_paths(container, prefix=args.source_prefix)
        if _matches(path, dataset=args.dataset, operation=args.operation)
    ]
    paths.sort()
    if args.max_source_blobs is not None:
        paths = paths[: args.max_source_blobs]
    if not paths:
        raise RuntimeError("No matching source Raw blobs found")

    source_records = 0
    output_records = 0
    created_blobs = 0
    reused_blobs = 0

    for source_index, source_path in enumerate(paths, start=1):
        records = _decode_jsonl_gzip(storage.download_bytes(container, source_path))
        grouped: dict[tuple[str, str, date], list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            dataset = str(record.get("dataset") or "").strip()
            operation = str(record.get("operation") or "").strip()
            if not dataset or not operation:
                raise ValueError(f"Missing dataset/operation in source blob: {source_path}")
            month = record_partition_month(record)
            grouped[(dataset, operation, month)].append(record)

        if sum(len(items) for items in grouped.values()) != len(records):
            raise RuntimeError(f"Record count mismatch while grouping {source_path}")

        for (dataset, operation, month), monthly_records in sorted(grouped.items()):
            if any(record_partition_month(record) != month for record in monthly_records):
                raise RuntimeError(
                    f"Month boundary violation before upload: {dataset}/{operation}/{month}"
                )
            blob, batch = writer.upload_items(
                dataset=dataset,
                operation=operation,
                items=[],
                extra_records=monthly_records,
                partition_date=month,
                page_number=None,
                migration=False,
                monthly_partition=True,
            )
            expected_prefix = (
                f"data-go-kr/{dataset.lower()}/operation={operation.lower()}/"
                f"year={month:%Y}/month={month:%m}/"
            )
            if not blob.path.startswith(expected_prefix) or "/day=" in blob.path:
                raise RuntimeError(f"Unexpected destination path: {blob.path}")
            output_records += batch.record_count
            if blob.created:
                created_blobs += 1
            else:
                reused_blobs += 1
            print(
                f"WRITE month={month:%Y-%m} rows={batch.record_count} "
                f"created={blob.created} path={blob.path}"
            )

        source_records += len(records)
        print(
            f"SOURCE {source_index}/{len(paths)} rows={len(records)} "
            f"groups={len(grouped)} path={source_path}"
        )

    if output_records != source_records:
        raise RuntimeError(
            f"Final record mismatch source={source_records} output={output_records}"
        )
    print(
        f"REPARTITION COMPLETE source_blobs={len(paths)} records={source_records} "
        f"created_blobs={created_blobs} reused_blobs={reused_blobs}"
    )


if __name__ == "__main__":
    main()
