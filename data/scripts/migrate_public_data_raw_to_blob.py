"""Stream legacy raw.public_data_record rows into canonical monthly Raw blobs."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from db.connection import build_engine, session_scope
from db.models import RawDataObject, RawMigrationManifest
from storage import RawBlobWriter


SOURCE_TABLE = "raw.public_data_record"
MANIFEST_SOURCE = "raw.public_data_record:monthly-v3"


def _parse_month(value: str) -> date:
    try:
        parsed = date.fromisoformat(f"{value}-01")
    except ValueError as error:
        raise argparse.ArgumentTypeError("--month must be YYYY-MM") from error
    if value != parsed.strftime("%Y-%m"):
        raise argparse.ArgumentTypeError("--month must be YYYY-MM")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream legacy PostgreSQL raw JSONB to canonical Azure Raw blobs by month."
    )
    parser.add_argument("--chunk-size", type=int, default=50_000)
    parser.add_argument("--dataset")
    parser.add_argument("--operation")
    parser.add_argument(
        "--month",
        type=_parse_month,
        help="Optional single month to migrate in YYYY-MM form.",
    )
    parser.add_argument(
        "--max-chunks", type=int, help="Safety limit for smoke tests; omit for all."
    )
    return parser.parse_args()


def _operations(engine, args: argparse.Namespace) -> list[tuple[str, str, date, int]]:
    clauses = []
    params: dict[str, Any] = {}
    if args.dataset:
        clauses.append("dataset = :dataset")
        params["dataset"] = args.dataset
    if args.operation:
        clauses.append("operation = :operation")
        params["operation"] = args.operation
    if args.month:
        clauses.append(
            "COALESCE(reference_date, created_at::date) >= :month_start "
            "AND COALESCE(reference_date, created_at::date) < :month_end"
        )
        params["month_start"] = args.month
        params["month_end"] = _next_month(args.month)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    partition_expr = "COALESCE(reference_date, created_at::date)"
    query = text(
        f"""
        SELECT dataset, operation,
               date_trunc('month', {partition_expr})::date AS partition_month,
               max(record_id) AS max_record_id
        FROM {SOURCE_TABLE}
        {where}
        GROUP BY dataset, operation, date_trunc('month', {partition_expr})
        ORDER BY dataset, operation, partition_month
        """
    )
    with engine.connect() as connection:
        return [
            (row.dataset, row.operation, row.partition_month, row.max_record_id)
            for row in connection.execute(query, params)
        ]


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _resume_after(engine, dataset: str, operation: str, partition_month: date) -> int:
    prefix = (
        f"data-go-kr/{dataset.lower()}/operation={operation.lower()}/"
        f"year={partition_month:%Y}/month={partition_month:%m}/"
    )
    query = text(
        """
        SELECT COALESCE(max(source_max_id), 0)
        FROM raw.public_data_migration_manifest
        WHERE source_table = :source_table
          AND dataset = :dataset
          AND operation = :operation
          AND status = 'complete'
          AND blob_path LIKE :prefix
        """
    )
    with engine.connect() as connection:
        return int(
            connection.scalar(
                query,
                {
                    "source_table": MANIFEST_SOURCE,
                    "dataset": dataset,
                    "operation": operation,
                    "prefix": prefix + "%",
                },
            )
            or 0
        )


def _load_chunk(
    engine,
    dataset: str,
    operation: str,
    partition_month: date,
    after_id: int,
    chunk_size: int,
) -> list[dict[str, Any]]:
    query = text(
        f"""
        SELECT record_id, dataset, operation, payload_hash, reference_date,
               stock_code, isin, corporation_registration_number,
               corporation_name, payload, created_at, updated_at
        FROM {SOURCE_TABLE}
        WHERE dataset = :dataset AND operation = :operation
          AND COALESCE(reference_date, created_at::date) >= :month_start
          AND COALESCE(reference_date, created_at::date) < :month_end
          AND record_id > :after_id
        ORDER BY record_id
        LIMIT :chunk_size
        """
    )
    with engine.connect().execution_options(stream_results=True) as connection:
        return [
            dict(row)
            for row in connection.execute(
                query,
                {
                    "dataset": dataset,
                    "operation": operation,
                    "month_start": partition_month,
                    "month_end": _next_month(partition_month),
                    "after_id": after_id,
                    "chunk_size": chunk_size,
                },
            ).mappings()
        ]


def _record_manifest(
    engine,
    *,
    dataset: str,
    operation: str,
    source_min_id: int,
    source_max_id: int,
    blob,
    batch,
    started_at: datetime,
) -> None:
    completed_at = datetime.now(timezone.utc)
    with session_scope(engine) as session:
        session.execute(
            insert(RawDataObject.__table__)
            .values(
                dataset=dataset,
                operation=operation,
                source="data-go-kr",
                container=blob.container,
                blob_path=blob.path,
                content_sha256=batch.content_sha256,
                batch_hash=batch.batch_hash,
                record_count=batch.record_count,
                file_size=blob.size,
                compression="gzip",
                status="available",
                collected_at=completed_at,
            )
            .on_conflict_do_nothing(index_elements=["container", "blob_path"])
        )
        session.execute(
            insert(RawMigrationManifest.__table__)
            .values(
                source_table=MANIFEST_SOURCE,
                dataset=dataset,
                operation=operation,
                source_min_id=source_min_id,
                source_max_id=source_max_id,
                migrated_row_count=batch.record_count,
                container=blob.container,
                blob_path=blob.path,
                blob_size=blob.size,
                content_sha256=batch.content_sha256,
                status="complete",
                started_at=started_at,
                completed_at=completed_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    "source_table",
                    "dataset",
                    "operation",
                    "source_min_id",
                    "source_max_id",
                ]
            )
        )


def main() -> None:
    args = parse_args()
    if args.chunk_size < 100:
        raise ValueError("--chunk-size must be at least 100")
    if args.max_chunks is not None and args.max_chunks < 1:
        raise ValueError("--max-chunks must be at least 1")

    engine = build_engine()
    writer = RawBlobWriter.from_env()
    completed_chunks = 0
    completed_rows = 0
    for dataset, operation, partition_month, max_record_id in _operations(engine, args):
        after_id = _resume_after(engine, dataset, operation, partition_month)
        while after_id < max_record_id:
            started_at = datetime.now(timezone.utc)
            rows = _load_chunk(
                engine,
                dataset,
                operation,
                partition_month,
                after_id,
                args.chunk_size,
            )
            if not rows:
                break

            # Preserve each API item exactly as it was stored in legacy Raw JSONB.
            items = [row["payload"] for row in rows]
            blob, batch = writer.upload_items(
                dataset=dataset,
                operation=operation,
                items=items,
                partition_date=partition_month,
                page_number=None,
                migration=False,
                monthly_partition=True,
                collected_at=rows[0]["created_at"],
            )
            source_min_id = rows[0]["record_id"]
            source_max_id = rows[-1]["record_id"]
            _record_manifest(
                engine,
                dataset=dataset,
                operation=operation,
                source_min_id=source_min_id,
                source_max_id=source_max_id,
                blob=blob,
                batch=batch,
                started_at=started_at,
            )
            after_id = source_max_id
            completed_chunks += 1
            completed_rows += len(rows)
            print(
                f"MIGRATED {dataset}/{operation} month={partition_month:%Y-%m} "
                f"ids={source_min_id}..{source_max_id} rows={len(rows)} "
                f"bytes={blob.size} chunks={completed_chunks} run_rows={completed_rows}"
            )
            if args.max_chunks and completed_chunks >= args.max_chunks:
                print("Stopped at --max-chunks safety limit; rerun to resume.")
                return
        print(f"DONE {dataset}/{operation} month={partition_month:%Y-%m} after_id={after_id}")


if __name__ == "__main__":
    main()
