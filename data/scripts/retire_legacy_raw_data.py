"""Verify canonical Raw Blob parity, then optionally truncate legacy SQL Raw data.

This is the destructive retirement gate for ``raw.public_data_record``. Azure Blob
is the Raw source of truth. The command scans every canonical Raw object, validates
its compressed checksum and every payload hash, and proves that each historical
Blob record maps to the same PostgreSQL landing-table row by ``legacy.recordId``.
Only after the full verification succeeds may ``--truncate-after-verify`` remove
the duplicated SQL Raw rows. The table, migration manifests, and Blob catalog are
kept so schema history and migration audit evidence remain available.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from sqlalchemy import select, text

from db.connection import build_engine
from db.models import PublicDataRecord
from scripts.reconcile_raw_blob_catalog import CANONICAL_RAW_RE, list_canonical_catalog
from storage import BlobStorage
from storage.raw import payload_hash as compute_payload_hash


SOURCE_TABLE = "raw.public_data_record"


@dataclass(frozen=True)
class SourceSignature:
    row_count: int
    max_record_id: int
    max_updated_at: datetime | None


class RecordIdBitmap:
    """Compact duplicate detector for positive legacy identity values."""

    def __init__(self, max_record_id: int) -> None:
        if max_record_id < 0:
            raise ValueError("max_record_id must not be negative")
        self.max_record_id = max_record_id
        self.bits = bytearray((max_record_id // 8) + 1)

    def add(self, record_id: int) -> bool:
        """Return False when record_id was already seen."""
        if record_id < 1 or record_id > self.max_record_id:
            raise ValueError(
                f"legacy recordId out of SQL range: {record_id} max={self.max_record_id}"
            )
        byte_index, bit_index = divmod(record_id, 8)
        mask = 1 << bit_index
        if self.bits[byte_index] & mask:
            return False
        self.bits[byte_index] |= mask
        return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify canonical Blob parity before retiring legacy PostgreSQL Raw rows."
    )
    parser.add_argument(
        "--truncate-after-verify",
        action="store_true",
        help="TRUNCATE raw.public_data_record only after every verification gate passes.",
    )
    parser.add_argument("--expected-blob-count", type=int, default=4_228)
    parser.add_argument("--sql-batch-size", type=int, default=5_000)
    parser.add_argument("--samples-per-operation", type=int, default=3)
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Optional dotenv file. Existing environment variables take precedence.",
    )
    return parser.parse_args()


def source_signature(connection) -> SourceSignature:
    row = connection.execute(
        text(
            f"""
            SELECT count(*)::bigint AS row_count,
                   COALESCE(max(record_id), 0)::bigint AS max_record_id,
                   max(updated_at) AS max_updated_at
            FROM {SOURCE_TABLE}
            """
        )
    ).mappings().one()
    return SourceSignature(
        row_count=int(row["row_count"]),
        max_record_id=int(row["max_record_id"]),
        max_updated_at=row["max_updated_at"],
    )


def database_dependencies(connection) -> list[str]:
    dependencies: list[str] = []
    for row in connection.execute(
        text(
            """
            SELECT conrelid::regclass::text AS relation, conname
            FROM pg_constraint
            WHERE contype = 'f'
              AND confrelid = 'raw.public_data_record'::regclass
            ORDER BY 1, 2
            """
        )
    ):
        dependencies.append(f"FK {row.relation}.{row.conname}")
    for row in connection.execute(
        text(
            """
            SELECT DISTINCT view_schema, view_name
            FROM information_schema.view_table_usage
            WHERE table_schema = 'raw' AND table_name = 'public_data_record'
            ORDER BY 1, 2
            """
        )
    ):
        dependencies.append(f"VIEW {row.view_schema}.{row.view_name}")
    return dependencies


def _chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def validate_raw_record(
    record: dict[str, Any],
    *,
    path_dataset: str,
    path_operation: str,
    path_year: int,
    path_month: int,
) -> tuple[int | None, str, dict[str, Any]]:
    dataset = str(record.get("dataset") or "").strip()
    operation = str(record.get("operation") or "").strip()
    if dataset.lower() != path_dataset.lower():
        raise ValueError(
            f"record/path dataset mismatch: record={dataset} path={path_dataset}"
        )
    if operation.lower() != path_operation.lower():
        raise ValueError(
            f"record/path operation mismatch: record={operation} path={path_operation}"
        )

    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Raw record payload must be an object")
    observed_hash = str(record.get("payloadHash") or "")
    calculated_hash = compute_payload_hash(payload)
    if observed_hash != calculated_hash:
        raise ValueError(
            f"payload hash mismatch dataset={dataset} operation={operation}"
        )

    bas_dt = str(payload.get("basDt") or "").strip()
    if len(bas_dt) != 8 or not bas_dt.isdigit():
        raise ValueError(
            f"Raw record requires YYYYMMDD basDt dataset={dataset} operation={operation}"
        )
    if int(bas_dt[:4]) != path_year or int(bas_dt[4:6]) != path_month:
        raise ValueError(
            "basDt/path partition mismatch "
            f"basDt={bas_dt} path={path_year:04d}-{path_month:02d}"
        )

    legacy = record.get("legacy")
    record_id: int | None = None
    if isinstance(legacy, dict) and legacy.get("recordId") is not None:
        try:
            record_id = int(legacy["recordId"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid legacy.recordId: {legacy.get('recordId')!r}") from exc
    return record_id, observed_hash, payload


def compare_sql_batch(connection, items: list[tuple[int, str, str, str]]) -> None:
    """Compare record_id, dataset, operation, and payload_hash for one Blob batch."""
    ids = [item[0] for item in items]
    statement = select(
        PublicDataRecord.record_id,
        PublicDataRecord.dataset,
        PublicDataRecord.operation,
        PublicDataRecord.payload_hash,
    ).where(PublicDataRecord.record_id.in_(ids))
    rows = {
        int(row.record_id): row
        for row in connection.execute(statement).all()
    }
    if len(rows) != len(ids):
        missing = [record_id for record_id in ids if record_id not in rows]
        raise RuntimeError(f"SQL Raw is missing legacy record IDs: {missing[:20]}")
    for record_id, dataset, operation, blob_hash in items:
        row = rows[record_id]
        if row.dataset != dataset or row.operation != operation:
            raise RuntimeError(
                "SQL/Blob identity mismatch "
                f"record_id={record_id} blob={dataset}/{operation} "
                f"sql={row.dataset}/{row.operation}"
            )
        if row.payload_hash != blob_hash:
            raise RuntimeError(
                f"SQL/Blob payload_hash mismatch record_id={record_id}"
            )


def compare_exact_samples(connection, samples: dict[int, dict[str, Any]]) -> None:
    if not samples:
        raise RuntimeError("No historical Blob payload samples were collected")
    ids = sorted(samples)
    statement = select(PublicDataRecord.record_id, PublicDataRecord.payload).where(
        PublicDataRecord.record_id.in_(ids)
    )
    rows = {
        int(row.record_id): row.payload
        for row in connection.execute(statement).all()
    }
    if len(rows) != len(ids):
        missing = [record_id for record_id in ids if record_id not in rows]
        raise RuntimeError(f"SQL Raw sample IDs missing: {missing[:20]}")
    for record_id, blob_payload in samples.items():
        if rows[record_id] != blob_payload:
            raise RuntimeError(
                f"Exact SQL JSONB / Blob payload mismatch record_id={record_id}"
            )


def verify_catalog_paths(connection, *, container: str, blob_paths: set[str]) -> None:
    rows = connection.execute(
        text(
            """
            SELECT blob_path
            FROM raw.data_object
            WHERE container = :container
              AND source = 'data-go-kr'
              AND status = 'available'
              AND blob_path LIKE 'data-go-kr/%'
            """
        ),
        {"container": container},
    )
    catalog_paths = {str(row.blob_path) for row in rows}
    if catalog_paths != blob_paths:
        missing = sorted(blob_paths - catalog_paths)[:10]
        stale = sorted(catalog_paths - blob_paths)[:10]
        raise RuntimeError(
            "Blob/PostgreSQL catalog path mismatch "
            f"missing_in_db={missing} stale_in_db={stale}"
        )


def main() -> None:
    args = parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    if args.expected_blob_count < 1:
        raise ValueError("--expected-blob-count must be at least 1")
    if args.sql_batch_size < 1 or args.sql_batch_size > 10_000:
        raise ValueError("--sql-batch-size must be between 1 and 10000")
    if args.samples_per_operation < 1:
        raise ValueError("--samples-per-operation must be at least 1")
    if args.progress_every < 1:
        raise ValueError("--progress-every must be at least 1")

    engine = build_engine()
    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")

    with engine.connect() as connection:
        exists = connection.scalar(
            text("SELECT to_regclass('raw.public_data_record') IS NOT NULL")
        )
        if not exists:
            print("SQL RAW ALREADY RETIRED table=raw.public_data_record")
            return
        initial = source_signature(connection)
        dependencies = database_dependencies(connection)
        if dependencies:
            raise RuntimeError(
                "Refusing Raw retirement because DB dependencies exist: "
                + "; ".join(dependencies)
            )

    if initial.row_count < 1 or initial.max_record_id < 1:
        print("SQL RAW ALREADY EMPTY table=raw.public_data_record")
        return

    catalog = list_canonical_catalog(storage, container)
    if len(catalog) != args.expected_blob_count:
        raise RuntimeError(
            f"canonical Blob count mismatch actual={len(catalog)} "
            f"expected={args.expected_blob_count}"
        )

    print(
        "RETIRE VERIFY START "
        f"sql_rows={initial.row_count} max_record_id={initial.max_record_id} "
        f"canonical_blobs={len(catalog)}"
    )
    seen = RecordIdBitmap(initial.max_record_id)
    legacy_count = 0
    blob_only_count = 0
    total_blob_records = 0
    samples: dict[int, dict[str, Any]] = {}
    sample_counts: dict[tuple[str, str], int] = {}
    blob_paths: set[str] = set()

    with engine.connect() as connection:
        for blob_index, catalog_row in enumerate(catalog, start=1):
            path = str(catalog_row["blob_path"])
            match = CANONICAL_RAW_RE.match(path)
            if match is None:
                raise RuntimeError(f"non-canonical path reached verifier: {path}")
            data = storage.download_bytes(container, path)
            actual_sha = hashlib.sha256(data).hexdigest()
            if actual_sha != catalog_row["content_sha256"]:
                raise RuntimeError(f"compressed checksum mismatch: {path}")

            legacy_items: list[tuple[int, str, str, str]] = []
            decoded_count = 0
            with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as stream:
                for raw_line in stream:
                    if not raw_line.strip():
                        continue
                    decoded_count += 1
                    record = json.loads(raw_line)
                    record_id, observed_hash, payload = validate_raw_record(
                        record,
                        path_dataset=match.group("dataset"),
                        path_operation=match.group("operation"),
                        path_year=int(match.group("year")),
                        path_month=int(match.group("month")),
                    )
                    dataset = str(record["dataset"])
                    operation = str(record["operation"])
                    if record_id is None:
                        blob_only_count += 1
                        continue
                    if not seen.add(record_id):
                        raise RuntimeError(
                            f"duplicate legacy recordId across canonical Blob: {record_id}"
                        )
                    legacy_count += 1
                    legacy_items.append(
                        (record_id, dataset, operation, observed_hash)
                    )
                    sample_key = (dataset, operation)
                    sample_count = sample_counts.get(sample_key, 0)
                    if sample_count < args.samples_per_operation:
                        samples[record_id] = payload
                        sample_counts[sample_key] = sample_count + 1

                    if len(legacy_items) >= args.sql_batch_size:
                        compare_sql_batch(connection, legacy_items)
                        legacy_items.clear()

            if legacy_items:
                compare_sql_batch(connection, legacy_items)
            if decoded_count != int(catalog_row["record_count"]):
                raise RuntimeError(
                    f"Blob metadata record_count mismatch path={path} "
                    f"decoded={decoded_count} metadata={catalog_row['record_count']}"
                )
            total_blob_records += decoded_count
            blob_paths.add(path)
            if blob_index == 1 or blob_index % args.progress_every == 0 or blob_index == len(catalog):
                print(
                    "RETIRE VERIFY PROGRESS "
                    f"blobs={blob_index}/{len(catalog)} "
                    f"legacy_rows={legacy_count} blob_only_rows={blob_only_count}"
                )

        if legacy_count != initial.row_count:
            raise RuntimeError(
                "Historical Blob coverage does not equal SQL Raw count "
                f"blob_legacy={legacy_count} sql={initial.row_count}"
            )
        compare_exact_samples(connection, samples)
        verify_catalog_paths(connection, container=container, blob_paths=blob_paths)

    print(
        "RETIRE VERIFICATION PASSED "
        f"sql_rows={initial.row_count} legacy_blob_rows={legacy_count} "
        f"blob_only_rows={blob_only_count} total_blob_rows={total_blob_records} "
        f"exact_payload_samples={len(samples)} canonical_blobs={len(catalog)}"
    )

    if not args.truncate_after_verify:
        print("DRY RUN: SQL Raw data was not deleted")
        return

    # Prevent any concurrent landing-table write between the verified signature and
    # the destructive operation. DROP/CASCADE is intentionally not used: only the
    # duplicate Raw rows are retired while schema/audit structures remain.
    with engine.begin() as connection:
        connection.execute(text(f"LOCK TABLE {SOURCE_TABLE} IN ACCESS EXCLUSIVE MODE"))
        final = source_signature(connection)
        if final != initial:
            raise RuntimeError(
                "SQL Raw changed during verification; refusing TRUNCATE "
                f"initial={initial} final={final}"
            )
        dependencies = database_dependencies(connection)
        if dependencies:
            raise RuntimeError(
                "DB dependencies appeared during verification; refusing TRUNCATE: "
                + "; ".join(dependencies)
            )
        connection.execute(text(f"TRUNCATE TABLE {SOURCE_TABLE}"))

    with engine.connect() as connection:
        remaining = int(connection.scalar(text(f"SELECT count(*) FROM {SOURCE_TABLE}")) or 0)
        size_bytes = int(
            connection.scalar(
                text("SELECT pg_total_relation_size('raw.public_data_record')")
            )
            or 0
        )
    if remaining != 0:
        raise RuntimeError(f"TRUNCATE verification failed remaining_rows={remaining}")
    print(
        "SQL RAW RETIRED "
        f"rows_removed={initial.row_count} remaining_rows=0 size_bytes={size_bytes} "
        "table_preserved=true manifests_preserved=true catalog_preserved=true"
    )


if __name__ == "__main__":
    main()
