"""Reconcile canonical Raw Blob objects with PostgreSQL ``raw.data_object``.

The Azure Blob container is the source of truth for Raw API objects. This script
reads object metadata only (it never rewrites Raw payloads), validates the
canonical YYYY/MM path and object metadata, and optionally UPSERTs the searchable
catalog in PostgreSQL. Catalog rows for legacy Raw paths that no longer exist are
marked ``deleted`` rather than physically removed.
"""

from __future__ import annotations

import argparse
import calendar
import os
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert

from db.connection import build_engine, session_scope
from db.models import RawDataObject
from storage.blob import BlobStorage


CANONICAL_RAW_RE = re.compile(
    r"^data-go-kr/(?P<dataset>[^/]+)/operation=(?P<operation>[^/]+)/"
    r"year=(?P<year>\d{4})/month=(?P<month>\d{2})/(?P<file>[^/]+\.jsonl\.gz)$"
)
RAW_PREFIX = "data-go-kr/"
LEGACY_MIGRATION_PREFIX = "migration/data-go-kr/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit/reconcile Azure Raw Blob objects and raw.data_object."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write catalog changes to PostgreSQL. Without this flag, audit only.",
    )
    parser.add_argument(
        "--expected-minimum",
        type=int,
        default=1,
        help="Abort if fewer canonical objects exist than this safety threshold.",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    return parser.parse_args()


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    if month < 1 or month > 12:
        raise ValueError(f"invalid month: {month}")
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def build_catalog_row(
    *,
    container: str,
    path: str,
    size: int,
    metadata: dict[str, str] | None,
    created_at: datetime | None,
) -> dict[str, Any]:
    """Build one validated catalog row from a canonical Raw Blob listing."""

    match = CANONICAL_RAW_RE.match(path)
    if match is None:
        raise ValueError(f"not a canonical monthly Raw path: {path}")

    meta = dict(metadata or {})
    required = ("content_sha256", "batch_hash", "record_count")
    missing = [key for key in required if not str(meta.get(key, "")).strip()]
    if missing:
        raise ValueError(f"missing Blob metadata {missing}: {path}")

    dataset = match.group("dataset")
    operation = match.group("operation")
    metadata_dataset = str(meta.get("dataset", dataset)).strip()
    metadata_operation = str(meta.get("operation", operation)).strip()
    if metadata_dataset.lower() != dataset.lower():
        raise ValueError(
            f"dataset metadata/path mismatch: path={dataset} metadata={metadata_dataset}"
        )
    if metadata_operation.lower() != operation.lower():
        raise ValueError(
            "operation metadata/path mismatch: "
            f"path={operation} metadata={metadata_operation}"
        )

    try:
        record_count = int(meta["record_count"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid record_count metadata: {path}") from exc
    if record_count < 1:
        raise ValueError(f"record_count must be positive: {path}")

    year = int(match.group("year"))
    month = int(match.group("month"))
    range_start, range_end = _month_bounds(year, month)

    observed_at = created_at or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)

    return {
        "dataset": metadata_dataset,
        "operation": metadata_operation,
        "source": str(meta.get("source") or "data-go-kr"),
        "container": container,
        "blob_path": path,
        "content_sha256": meta["content_sha256"],
        "batch_hash": meta["batch_hash"],
        "record_count": record_count,
        "range_start": range_start,
        "range_end": range_end,
        "file_size": int(size),
        "compression": "gzip",
        "status": "available",
        "collected_at": observed_at,
    }


def list_canonical_catalog(storage: BlobStorage, container: str) -> list[dict[str, Any]]:
    """List canonical Raw objects with metadata without downloading object bodies."""

    container_client = storage.service_client.get_container_client(container)
    rows: list[dict[str, Any]] = []
    for blob in container_client.list_blobs(
        name_starts_with=RAW_PREFIX, include=["metadata"]
    ):
        path = str(blob.name)
        if CANONICAL_RAW_RE.match(path) is None:
            raise ValueError(f"unexpected non-canonical Raw path under {RAW_PREFIX}: {path}")
        rows.append(
            build_catalog_row(
                container=container,
                path=path,
                size=int(blob.size or 0),
                metadata=dict(blob.metadata or {}),
                created_at=getattr(blob, "creation_time", None)
                or getattr(blob, "last_modified", None),
            )
        )
    rows.sort(key=lambda row: row["blob_path"])
    return rows


def reconcile_catalog(rows: list[dict[str, Any]], *, batch_size: int) -> tuple[int, int]:
    """UPSERT canonical objects and mark missing legacy catalog rows deleted."""

    engine = build_engine()
    canonical_paths = {row["blob_path"] for row in rows}
    upserted = 0
    stale_marked = 0

    with session_scope(engine) as session:
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            statement = insert(RawDataObject.__table__).values(batch)
            excluded = statement.excluded
            statement = statement.on_conflict_do_update(
                index_elements=["container", "blob_path"],
                set_={
                    "dataset": excluded.dataset,
                    "operation": excluded.operation,
                    "source": excluded.source,
                    "content_sha256": excluded.content_sha256,
                    "batch_hash": excluded.batch_hash,
                    "record_count": excluded.record_count,
                    "range_start": excluded.range_start,
                    "range_end": excluded.range_end,
                    "file_size": excluded.file_size,
                    "compression": excluded.compression,
                    "status": "available",
                    "collected_at": excluded.collected_at,
                    "updated_at": text("now()"),
                },
            )
            result = session.execute(statement)
            upserted += max(result.rowcount, 0)

        existing = list(
            session.execute(
                select(RawDataObject.data_object_id, RawDataObject.blob_path).where(
                    RawDataObject.container == rows[0]["container"],
                    RawDataObject.source == "data-go-kr",
                )
            )
        )
        stale_ids = [
            object_id
            for object_id, path in existing
            if (
                path.startswith(RAW_PREFIX)
                or path.startswith(LEGACY_MIGRATION_PREFIX)
            )
            and path not in canonical_paths
        ]
        for start in range(0, len(stale_ids), batch_size):
            ids = stale_ids[start : start + batch_size]
            if not ids:
                continue
            result = session.execute(
                update(RawDataObject)
                .where(RawDataObject.data_object_id.in_(ids))
                .values(status="deleted", updated_at=text("now()"))
            )
            stale_marked += max(result.rowcount, 0)

    return upserted, stale_marked


def main() -> None:
    args = parse_args()
    if args.expected_minimum < 1:
        raise ValueError("--expected-minimum must be at least 1")
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1")

    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    rows = list_canonical_catalog(storage, container)
    if len(rows) < args.expected_minimum:
        raise RuntimeError(
            f"Refusing reconciliation: canonical objects={len(rows)} "
            f"expected_minimum={args.expected_minimum}"
        )

    total_records = sum(row["record_count"] for row in rows)
    total_bytes = sum(row["file_size"] for row in rows)
    datasets = sorted({row["dataset"] for row in rows})
    print(
        "RAW CATALOG AUDIT OK "
        f"objects={len(rows)} records={total_records} bytes={total_bytes} "
        f"datasets={','.join(datasets)}"
    )

    if not args.apply:
        print("DRY RUN: PostgreSQL was not modified")
        return

    upserted, stale_marked = reconcile_catalog(rows, batch_size=args.batch_size)
    print(
        "RAW CATALOG RECONCILE COMPLETE "
        f"objects={len(rows)} upserted={upserted} stale_marked_deleted={stale_marked}"
    )


if __name__ == "__main__":
    main()
