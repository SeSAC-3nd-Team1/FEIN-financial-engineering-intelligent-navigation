"""Stream legacy raw.public_data_record rows into resumable JSONL/gzip blobs."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from db.connection import build_engine, session_scope
from db.models import RawDataObject, RawMigrationManifest
from storage import RawBlobWriter


SOURCE_TABLE = "raw.public_data_record"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream legacy PostgreSQL raw JSONB to Azure Blob Storage."
    )
    parser.add_argument("--chunk-size", type=int, default=10_000)
    parser.add_argument("--dataset")
    parser.add_argument("--operation")
    parser.add_argument(
        "--max-chunks", type=int, help="Safety limit for smoke tests; omit for all."
    )
    return parser.parse_args()


def _legacy_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": row["dataset"],
        "operation": row["operation"],
        "source": "data-go-kr",
        "collectedAt": row["created_at"],
        "payloadHash": row["payload_hash"],
        "payload": row["payload"],
        "legacy": {
            "sourceTable": SOURCE_TABLE,
            "recordId": row["record_id"],
            "referenceDate": row["reference_date"],
            "stockCode": row["stock_code"],
            "isin": row["isin"],
            "corporationRegistrationNumber": row[
                "corporation_registration_number"
            ],
            "corporationName": row["corporation_name"],
            "updatedAt": row["updated_at"],
        },
    }


def _operations(engine, args: argparse.Namespace) -> list[tuple[str, str, int]]:
    clauses = []
    params: dict[str, Any] = {}
    if args.dataset:
        clauses.append("dataset = :dataset")
        params["dataset"] = args.dataset
    if args.operation:
        clauses.append("operation = :operation")
        params["operation"] = args.operation
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with engine.connect() as connection:
        return [
            (row.dataset, row.operation, row.max_record_id)
            for row in connection.execute(
                text(
                    f"SELECT dataset, operation, max(record_id) AS max_record_id "
                    f"FROM {SOURCE_TABLE} {where} GROUP BY dataset, operation "
                    "ORDER BY dataset, operation"
                ),
                params,
            )
        ]


def _resume_after(engine, dataset: str, operation: str) -> int:
    with session_scope(engine) as session:
        return (
            session.scalar(
                select(func.max(RawMigrationManifest.source_max_id)).where(
                    RawMigrationManifest.source_table == SOURCE_TABLE,
                    RawMigrationManifest.dataset == dataset,
                    RawMigrationManifest.operation == operation,
                    RawMigrationManifest.status == "complete",
                )
            )
            or 0
        )


def _load_chunk(
    engine, dataset: str, operation: str, after_id: int, chunk_size: int
) -> list[dict[str, Any]]:
    query = text(
        f"""
        SELECT record_id, dataset, operation, payload_hash, reference_date,
               stock_code, isin, corporation_registration_number,
               corporation_name, payload, created_at, updated_at
        FROM {SOURCE_TABLE}
        WHERE dataset = :dataset AND operation = :operation
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
                source_table=SOURCE_TABLE,
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
    if args.chunk_size < 100 or args.chunk_size > 50_000:
        raise ValueError("--chunk-size must be between 100 and 50000")
    if args.max_chunks is not None and args.max_chunks < 1:
        raise ValueError("--max-chunks must be at least 1")

    engine = build_engine()
    writer = RawBlobWriter.from_env()
    completed_chunks = 0
    completed_rows = 0
    for dataset, operation, max_record_id in _operations(engine, args):
        after_id = _resume_after(engine, dataset, operation)
        while after_id < max_record_id:
            started_at = datetime.now(timezone.utc)
            rows = _load_chunk(
                engine, dataset, operation, after_id, args.chunk_size
            )
            if not rows:
                raise RuntimeError(
                    f"source chunk unexpectedly empty before max id {max_record_id}"
                )
            records = [_legacy_record(row) for row in rows]
            partition_date = (
                rows[0]["reference_date"]
                or rows[0]["created_at"].date()
                or date.today()
            )
            blob, batch = writer.upload_items(
                dataset=dataset,
                operation=operation,
                items=[],
                extra_records=records,
                partition_date=partition_date,
                page_number=None,
                migration=True,
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
                f"MIGRATED {dataset}/{operation} ids={source_min_id}..{source_max_id} "
                f"rows={len(rows)} bytes={blob.size} chunks={completed_chunks} "
                f"run_rows={completed_rows}"
            )
            if args.max_chunks and completed_chunks >= args.max_chunks:
                print("Stopped at --max-chunks safety limit; rerun to resume.")
                return
        print(f"DONE {dataset}/{operation} after_id={after_id}")


if __name__ == "__main__":
    main()
