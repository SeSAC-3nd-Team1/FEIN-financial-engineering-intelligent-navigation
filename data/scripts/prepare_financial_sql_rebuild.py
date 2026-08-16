"""Preserve API-origin normalized payloads in Raw Blob, then reset financial SQL data.

This command is the destructive gate before rebuilding the financial PostgreSQL
layer from Azure Raw Blob. Membership data is explicitly out of scope and must
remain untouched.

Workflow:
1. Inventory financial tables and membership-table counts.
2. Hash every API-origin ``source_payload`` in normalized financial tables.
3. Scan canonical Raw Blob records and remove hashes already preserved there.
4. Optionally upload only SQL-only API payloads to canonical monthly Raw paths.
5. Refuse reset if any API payload is still not preserved in Blob.
6. TRUNCATE only the known financial/raw tables (never CASCADE), preserving
   ``users``, ``terms``, ``user_agreements`` and ``alembic_version``.

The default mode is read-only. Use ``--sync-missing-to-blob`` to write missing
Raw objects and ``--reset-after-sync`` to clear the financial PostgreSQL data
only after every preservation gate succeeds.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import sqlite3
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from sqlalchemy import bindparam, text

from db.connection import build_engine
from scripts.reconcile_raw_blob_catalog import CANONICAL_RAW_RE, list_canonical_catalog
from scripts.retire_legacy_raw_data import validate_raw_record
from storage import BlobStorage, RawBlobWriter
from storage.raw import payload_hash as compute_payload_hash


@dataclass(frozen=True)
class ApiSource:
    table_name: str
    pk_name: str
    source: str
    dataset: str
    operation: str


API_SOURCES = (
    ApiSource(
        "raw.stock_master",
        "stock_id",
        "DATA_GO_KR_KRX_LISTED",
        "stock_master",
        "getItemInfo",
    ),
    ApiSource(
        "raw.stock_master",
        "stock_id",
        "DATA_GO_KR_STOCK_PRICE_DERIVED_MASTER",
        "stock_price",
        "getStockPriceInfo",
    ),
    ApiSource(
        "raw.stock_price_daily",
        "price_id",
        "DATA_GO_KR_STOCK_PRICE",
        "stock_price",
        "getStockPriceInfo",
    ),
    ApiSource(
        "raw.market_index_daily",
        "market_index_id",
        "DATA_GO_KR_MARKET_INDEX",
        "market_index",
        "getStockMarketIndex",
    ),
)

# Only these tables are cleared. Public membership tables are deliberately absent.
FINANCIAL_RESET_TABLES = (
    "raw.stock_price_daily",
    "raw.stock_issuance",
    "raw.financial_statement",
    "raw.stock_master",
    "raw.market_index_daily",
    "raw.macro_indicator",
    "raw.public_data_record",
    "raw.public_data_collection_checkpoint",
    "raw.data_object",
    "raw.public_data_migration_manifest",
)

MEMBERSHIP_TABLES = (
    "public.users",
    "public.terms",
    "public.user_agreements",
)

PRESERVED_TABLES = MEMBERSHIP_TABLES + ("public.alembic_version",)

SOURCE_PAYLOAD_TABLES = (
    "raw.stock_master",
    "raw.stock_price_daily",
    "raw.market_index_daily",
    "raw.stock_issuance",
    "raw.financial_statement",
    "raw.macro_indicator",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preserve SQL-only API payloads in Raw Blob before resetting only the "
            "financial PostgreSQL data. Membership tables are always preserved."
        )
    )
    parser.add_argument(
        "--sync-missing-to-blob",
        action="store_true",
        help="Upload API source_payload values that are not already in canonical Raw Blob.",
    )
    parser.add_argument(
        "--reset-after-sync",
        action="store_true",
        help=(
            "TRUNCATE the known financial/raw tables after Blob parity is proven. "
            "Requires --sync-missing-to-blob even when zero payloads are missing."
        ),
    )
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument("--sql-fetch-size", type=int, default=5_000)
    parser.add_argument("--upload-batch-size", type=int, default=5_000)
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Optional dotenv file. Existing environment variables take precedence.",
    )
    return parser.parse_args()


def _split_table(fullname: str) -> tuple[str, str]:
    schema, table = fullname.split(".", 1)
    return schema, table


def table_exists(connection, fullname: str) -> bool:
    return bool(connection.scalar(text("SELECT to_regclass(:name) IS NOT NULL"), {"name": fullname}))


def count_table(connection, fullname: str) -> int:
    if not table_exists(connection, fullname):
        return 0
    return int(connection.scalar(text(f"SELECT count(*) FROM {fullname}")) or 0)


def membership_counts(connection) -> dict[str, int]:
    return {name: count_table(connection, name) for name in MEMBERSHIP_TABLES}


def print_source_inventory(connection) -> None:
    print("FINANCIAL SOURCE INVENTORY")
    for fullname in SOURCE_PAYLOAD_TABLES:
        if not table_exists(connection, fullname):
            print(f"source table={fullname} missing=true")
            continue
        rows = connection.execute(
            text(
                f"""
                SELECT source,
                       count(*)::bigint AS rows,
                       count(*) FILTER (WHERE source_payload IS NULL)::bigint AS null_payloads,
                       count(*) FILTER (WHERE source_payload IS NOT NULL)::bigint AS payloads
                FROM {fullname}
                GROUP BY source
                ORDER BY source
                """
            )
        ).mappings()
        for row in rows:
            print(
                f"source table={fullname} source={row['source']} rows={int(row['rows'])} "
                f"payloads={int(row['payloads'])} null_payloads={int(row['null_payloads'])}"
            )


def _api_source_by_table_source() -> dict[tuple[str, str], ApiSource]:
    return {(item.table_name, item.source): item for item in API_SOURCES}


def validate_unmapped_payload_sources(connection) -> None:
    mapped = _api_source_by_table_source()
    failures: list[str] = []
    for fullname in SOURCE_PAYLOAD_TABLES:
        if not table_exists(connection, fullname):
            continue
        rows = connection.execute(
            text(
                f"""
                SELECT source, count(*)::bigint AS rows
                FROM {fullname}
                WHERE source_payload IS NOT NULL
                GROUP BY source
                ORDER BY source
                """
            )
        )
        for source, count in rows:
            if (fullname, str(source)) not in mapped:
                failures.append(
                    f"unmapped source_payload table={fullname} source={source} rows={int(count)}"
                )
    if failures:
        raise RuntimeError(
            "Refusing financial SQL reset because source_payload rows exist for an "
            "unmapped origin; map/preserve them first: " + "; ".join(failures)
        )


def build_pending_index(engine, db: sqlite3.Connection, fetch_size: int) -> tuple[int, int]:
    db.execute(
        """
        CREATE TABLE pending (
            dataset TEXT NOT NULL,
            operation TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            table_name TEXT NOT NULL,
            pk_name TEXT NOT NULL,
            pk_value INTEGER NOT NULL,
            source TEXT NOT NULL,
            PRIMARY KEY (dataset, operation, payload_hash)
        ) WITHOUT ROWID
        """
    )
    inserted_rows = 0
    duplicate_payload_rows = 0
    with engine.connect().execution_options(stream_results=True) as connection:
        for spec in API_SOURCES:
            if not table_exists(connection, spec.table_name):
                continue
            result = connection.execution_options(yield_per=fetch_size).execute(
                text(
                    f"""
                    SELECT {spec.pk_name} AS pk_value, source_payload
                    FROM {spec.table_name}
                    WHERE source = :source
                    ORDER BY {spec.pk_name}
                    """
                ),
                {"source": spec.source},
            ).mappings()
            batch: list[tuple[str, str, str, str, str, int, str]] = []
            for row in result:
                payload = row["source_payload"]
                if not isinstance(payload, dict):
                    raise RuntimeError(
                        "API-origin normalized row has no preservable source_payload "
                        f"table={spec.table_name} pk={row['pk_value']} source={spec.source}"
                    )
                digest = compute_payload_hash(payload)
                batch.append(
                    (
                        spec.dataset,
                        spec.operation,
                        digest,
                        spec.table_name,
                        spec.pk_name,
                        int(row["pk_value"]),
                        spec.source,
                    )
                )
                inserted_rows += 1
                if len(batch) >= fetch_size:
                    before = db.total_changes
                    db.executemany(
                        "INSERT OR IGNORE INTO pending VALUES (?, ?, ?, ?, ?, ?, ?)", batch
                    )
                    duplicate_payload_rows += len(batch) - (db.total_changes - before)
                    batch.clear()
            if batch:
                before = db.total_changes
                db.executemany(
                    "INSERT OR IGNORE INTO pending VALUES (?, ?, ?, ?, ?, ?, ?)", batch
                )
                duplicate_payload_rows += len(batch) - (db.total_changes - before)
            db.commit()
    return inserted_rows, duplicate_payload_rows


def _target_pairs() -> set[tuple[str, str]]:
    return {(item.dataset.lower(), item.operation.lower()) for item in API_SOURCES}


def scan_blob_and_remove_preserved(
    storage: BlobStorage,
    container: str,
    db: sqlite3.Connection,
    progress_every: int,
) -> tuple[int, int]:
    catalog = list_canonical_catalog(storage, container)
    target_pairs = _target_pairs()
    targets = [
        item
        for item in catalog
        if (
            str(item["dataset"]).lower(),
            str(item["operation"]).lower(),
        )
        in target_pairs
    ]
    if not targets:
        raise RuntimeError("No canonical Raw Blob objects matched normalized API sources")

    decoded_records = 0
    matched_deletes = 0
    for blob_index, item in enumerate(targets, start=1):
        path = str(item["blob_path"])
        match = CANONICAL_RAW_RE.match(path)
        if match is None:
            raise RuntimeError(f"non-canonical path reached API parity scan: {path}")
        data = storage.download_bytes(container, path)
        if hashlib.sha256(data).hexdigest() != str(item["content_sha256"]):
            raise RuntimeError(f"compressed checksum mismatch: {path}")

        delete_batch: list[tuple[str, str, str]] = []
        decoded_count = 0
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as stream:
            for raw_line in stream:
                if not raw_line.strip():
                    continue
                decoded_count += 1
                record = json.loads(raw_line)
                _, observed_hash, _ = validate_raw_record(
                    record,
                    path_dataset=match.group("dataset"),
                    path_operation=match.group("operation"),
                    path_year=int(match.group("year")),
                    path_month=int(match.group("month")),
                )
                delete_batch.append(
                    (
                        str(record["dataset"]),
                        str(record["operation"]),
                        observed_hash,
                    )
                )
                if len(delete_batch) >= 10_000:
                    before = db.total_changes
                    db.executemany(
                        "DELETE FROM pending WHERE lower(dataset)=lower(?) AND lower(operation)=lower(?) AND payload_hash=?",
                        delete_batch,
                    )
                    matched_deletes += db.total_changes - before
                    delete_batch.clear()
        if delete_batch:
            before = db.total_changes
            db.executemany(
                "DELETE FROM pending WHERE lower(dataset)=lower(?) AND lower(operation)=lower(?) AND payload_hash=?",
                delete_batch,
            )
            matched_deletes += db.total_changes - before
        db.commit()
        if decoded_count != int(item["record_count"]):
            raise RuntimeError(
                f"Raw Blob record_count mismatch path={path} decoded={decoded_count} "
                f"metadata={item['record_count']}"
            )
        decoded_records += decoded_count
        if blob_index == 1 or blob_index % progress_every == 0 or blob_index == len(targets):
            pending = int(db.execute("SELECT count(*) FROM pending").fetchone()[0])
            print(
                "SQL/BLOB PARITY PROGRESS "
                f"blobs={blob_index}/{len(targets)} decoded={decoded_records} pending={pending}"
            )
    return len(targets), decoded_records


def pending_counts(db: sqlite3.Connection) -> list[tuple[str, str, int]]:
    return [
        (str(dataset), str(operation), int(count))
        for dataset, operation, count in db.execute(
            """
            SELECT dataset, operation, count(*)
            FROM pending
            GROUP BY dataset, operation
            ORDER BY dataset, operation
            """
        )
    ]


def _parse_basdt_month(payload: dict[str, Any]) -> date:
    value = str(payload.get("basDt") or "").strip()
    if len(value) != 8 or not value.isdigit():
        raise RuntimeError(f"SQL-only API payload has invalid basDt={value!r}")
    try:
        parsed = datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise RuntimeError(f"SQL-only API payload has invalid basDt={value!r}") from exc
    return date(parsed.year, parsed.month, 1)


def _chunks(values: list[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def sync_pending_to_blob(
    engine,
    db: sqlite3.Connection,
    writer: RawBlobWriter,
    *,
    fetch_size: int,
    upload_batch_size: int,
) -> tuple[int, int, int]:
    rows = list(
        db.execute(
            """
            SELECT dataset, operation, payload_hash, table_name, pk_name, pk_value, source
            FROM pending
            ORDER BY table_name, pk_name, pk_value
            """
        )
    )
    if not rows:
        return 0, 0, 0

    by_table: dict[tuple[str, str], list[tuple[str, str, str, int, str]]] = defaultdict(list)
    for dataset, operation, digest, table_name, pk_name, pk_value, source in rows:
        by_table[(str(table_name), str(pk_name))].append(
            (str(dataset), str(operation), str(digest), int(pk_value), str(source))
        )

    buffers: dict[tuple[str, str, date], list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    uploaded_payloads = 0
    created_blobs = 0
    reused_blobs = 0

    def flush(key: tuple[str, str, date]) -> None:
        nonlocal uploaded_payloads, created_blobs, reused_blobs
        values = buffers.get(key) or []
        if not values:
            return
        dataset, operation, month = key
        expected_hashes = [digest for digest, _ in values]
        payloads = [payload for _, payload in values]
        blob, batch = writer.upload_items(
            dataset=dataset,
            operation=operation,
            items=payloads,
            partition_date=month,
            page_number=None,
            monthly_partition=True,
        )
        if batch.record_count != len(payloads):
            raise RuntimeError(
                f"Raw upload record mismatch dataset={dataset} operation={operation} "
                f"expected={len(payloads)} actual={batch.record_count}"
            )
        # Read the object back before marking SQL-only payloads as preserved.
        stored = writer.storage.download_bytes(blob.container, blob.path)
        if hashlib.sha256(stored).hexdigest() != batch.content_sha256:
            raise RuntimeError(f"new Raw Blob checksum mismatch: {blob.path}")
        observed_hashes: list[str] = []
        with gzip.GzipFile(fileobj=io.BytesIO(stored), mode="rb") as stream:
            for raw_line in stream:
                if raw_line.strip():
                    record = json.loads(raw_line)
                    observed_hashes.append(str(record.get("payloadHash") or ""))
        if observed_hashes != expected_hashes:
            raise RuntimeError(f"new Raw Blob payload hash/order mismatch: {blob.path}")
        db.executemany(
            "DELETE FROM pending WHERE dataset=? AND operation=? AND payload_hash=?",
            [(dataset, operation, digest) for digest in expected_hashes],
        )
        db.commit()
        uploaded_payloads += len(payloads)
        if blob.created:
            created_blobs += 1
        else:
            reused_blobs += 1
        print(
            "SQL-ONLY RAW PRESERVED "
            f"dataset={dataset} operation={operation} month={month:%Y-%m} "
            f"rows={len(payloads)} created={blob.created} path={blob.path}"
        )
        buffers[key].clear()

    with engine.connect() as connection:
        for (table_name, pk_name), entries in by_table.items():
            entry_by_pk = {pk: (dataset, operation, digest, source) for dataset, operation, digest, pk, source in entries}
            ids = sorted(entry_by_pk)
            statement = text(
                f"SELECT {pk_name} AS pk_value, source, source_payload FROM {table_name} "
                f"WHERE {pk_name} IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
            for id_batch in _chunks(ids, fetch_size):
                found = {
                    int(row["pk_value"]): row
                    for row in connection.execute(statement, {"ids": id_batch}).mappings()
                }
                missing_ids = sorted(set(id_batch) - found.keys())
                if missing_ids:
                    raise RuntimeError(
                        f"normalized SQL rows disappeared during preservation table={table_name} ids={missing_ids[:20]}"
                    )
                for pk_value in id_batch:
                    dataset, operation, expected_hash, expected_source = entry_by_pk[pk_value]
                    row = found[pk_value]
                    if str(row["source"]) != expected_source:
                        raise RuntimeError(
                            f"normalized SQL source changed during preservation table={table_name} pk={pk_value}"
                        )
                    payload = row["source_payload"]
                    if not isinstance(payload, dict):
                        raise RuntimeError(
                            f"normalized SQL source_payload disappeared table={table_name} pk={pk_value}"
                        )
                    actual_hash = compute_payload_hash(payload)
                    if actual_hash != expected_hash:
                        raise RuntimeError(
                            f"normalized SQL payload changed during preservation table={table_name} pk={pk_value}"
                        )
                    month = _parse_basdt_month(payload)
                    key = (dataset, operation, month)
                    buffers[key].append((expected_hash, payload))
                    if len(buffers[key]) >= upload_batch_size:
                        flush(key)

    for key in list(buffers):
        flush(key)
    return uploaded_payloads, created_blobs, reused_blobs


def list_user_tables(connection) -> list[str]:
    rows = connection.execute(
        text(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type='BASE TABLE'
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
              AND table_schema NOT LIKE 'pg_%'
            ORDER BY table_schema, table_name
            """
        )
    )
    return [f"{schema}.{table}" for schema, table in rows]


def external_financial_dependencies(connection) -> list[str]:
    reset = set(FINANCIAL_RESET_TABLES)
    dependencies: list[str] = []
    rows = connection.execute(
        text(
            """
            SELECT ns_src.nspname AS src_schema,
                   src.relname AS src_table,
                   con.conname,
                   ns_ref.nspname AS ref_schema,
                   ref.relname AS ref_table
            FROM pg_constraint con
            JOIN pg_class src ON src.oid = con.conrelid
            JOIN pg_namespace ns_src ON ns_src.oid = src.relnamespace
            JOIN pg_class ref ON ref.oid = con.confrelid
            JOIN pg_namespace ns_ref ON ns_ref.oid = ref.relnamespace
            WHERE con.contype='f'
            ORDER BY 1, 2, 3
            """
        )
    )
    for row in rows:
        source = f"{row.src_schema}.{row.src_table}"
        target = f"{row.ref_schema}.{row.ref_table}"
        if target in reset and source not in reset:
            dependencies.append(f"{source}.{row.conname}->{target}")
    return dependencies


def reset_financial_data(engine, membership_before: dict[str, int]) -> None:
    with engine.begin() as connection:
        deps = external_financial_dependencies(connection)
        if deps:
            raise RuntimeError(
                "Refusing financial reset because an untouched table references a reset table: "
                + "; ".join(deps)
            )
        existing = [name for name in FINANCIAL_RESET_TABLES if table_exists(connection, name)]
        if not existing:
            raise RuntimeError("No financial tables exist to reset")
        # Never CASCADE: if a dependency was missed, PostgreSQL must fail safely.
        connection.execute(
            text("TRUNCATE TABLE " + ", ".join(existing) + " RESTART IDENTITY")
        )

    with engine.connect() as connection:
        for name in FINANCIAL_RESET_TABLES:
            if table_exists(connection, name):
                remaining = count_table(connection, name)
                if remaining != 0:
                    raise RuntimeError(f"financial reset incomplete table={name} rows={remaining}")
        membership_after = membership_counts(connection)
        if membership_after != membership_before:
            raise RuntimeError(
                "Membership counts changed during financial reset "
                f"before={membership_before} after={membership_after}"
            )
        print(
            "FINANCIAL SQL RESET COMPLETE "
            f"tables={len([name for name in FINANCIAL_RESET_TABLES if table_exists(connection, name)])} "
            f"membership_preserved={membership_after}"
        )


def main() -> None:
    args = parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    if args.reset_after_sync and not args.sync_missing_to_blob:
        raise ValueError("--reset-after-sync requires --sync-missing-to-blob")
    if args.progress_every < 1:
        raise ValueError("--progress-every must be at least 1")
    if args.sql_fetch_size < 1 or args.sql_fetch_size > 20_000:
        raise ValueError("--sql-fetch-size must be between 1 and 20000")
    if args.upload_batch_size < 1 or args.upload_batch_size > 10_000:
        raise ValueError("--upload-batch-size must be between 1 and 10000")

    engine = build_engine()
    storage = BlobStorage.from_env()
    writer = RawBlobWriter.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")

    with engine.connect() as connection:
        membership_before = membership_counts(connection)
        print(f"MEMBERSHIP PRESERVE BEFORE counts={membership_before}")
        print_source_inventory(connection)
        validate_unmapped_payload_sources(connection)
        all_tables = list_user_tables(connection)
        untouched = sorted(
            set(all_tables) - set(FINANCIAL_RESET_TABLES) - set(PRESERVED_TABLES)
        )
        if untouched:
            print(f"UNTOUCHED OTHER TABLES count={len(untouched)} tables={untouched}")

    with tempfile.TemporaryDirectory(prefix="sesac-sql-rebuild-") as tmpdir:
        index_path = Path(tmpdir) / "pending.sqlite3"
        db = sqlite3.connect(index_path)
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("PRAGMA temp_store=MEMORY")
        db.execute("PRAGMA locking_mode=EXCLUSIVE")

        sql_api_rows, duplicates = build_pending_index(engine, db, args.sql_fetch_size)
        distinct_sql_payloads = int(db.execute("SELECT count(*) FROM pending").fetchone()[0])
        print(
            "SQL API INDEX COMPLETE "
            f"api_rows={sql_api_rows} distinct_payloads={distinct_sql_payloads} "
            f"duplicate_payload_rows={duplicates}"
        )

        scanned_blobs, decoded_records = scan_blob_and_remove_preserved(
            storage, container, db, args.progress_every
        )
        missing = pending_counts(db)
        missing_total = sum(count for _, _, count in missing)
        print(
            "SQL/BLOB PARITY RESULT "
            f"target_blobs={scanned_blobs} decoded_blob_records={decoded_records} "
            f"sql_only_payloads={missing_total} details={missing}"
        )

        if missing_total and not args.sync_missing_to_blob:
            print("DRY RUN: SQL-only API payloads found; Blob and SQL were not modified")
            return

        uploaded = created = reused = 0
        if missing_total:
            uploaded, created, reused = sync_pending_to_blob(
                engine,
                db,
                writer,
                fetch_size=args.sql_fetch_size,
                upload_batch_size=args.upload_batch_size,
            )
        remaining = int(db.execute("SELECT count(*) FROM pending").fetchone()[0])
        if remaining:
            raise RuntimeError(
                f"Refusing financial SQL reset: SQL-only API payloads remain={remaining}"
            )
        print(
            "API RAW PRESERVATION PASSED "
            f"original_sql_only={missing_total} uploaded={uploaded} "
            f"created_blobs={created} reused_blobs={reused} remaining=0"
        )
        db.close()

    if not args.reset_after_sync:
        print("SQL financial data was not reset; use --reset-after-sync after review")
        return

    # Recheck API-origin rows immediately before the destructive transaction. Any
    # newly inserted API row would have source_payload and therefore must not be
    # silently discarded. We use updated_at signatures for the mapped tables.
    with engine.connect() as connection:
        validate_unmapped_payload_sources(connection)
        membership_now = membership_counts(connection)
        if membership_now != membership_before:
            raise RuntimeError(
                "Membership data changed during preservation; refusing financial reset "
                f"before={membership_before} now={membership_now}"
            )

    reset_financial_data(engine, membership_before)


if __name__ == "__main__":
    main()
