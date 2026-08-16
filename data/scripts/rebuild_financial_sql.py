"""Fast front door for the guarded financial PostgreSQL rebuild preparation.

The shared safety logic lives in ``prepare_financial_sql_rebuild``. This module
replaces only the Blob/parity scanner so SQLite can use the composite primary
key directly for millions of payload-hash lookups, then delegates to the same
preservation and membership-safe reset workflow.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import sqlite3

from scripts import prepare_financial_sql_rebuild as core
from scripts.reconcile_raw_blob_catalog import CANONICAL_RAW_RE, list_canonical_catalog
from scripts.retire_legacy_raw_data import validate_raw_record
from storage import BlobStorage


def scan_blob_and_remove_preserved(
    storage: BlobStorage,
    container: str,
    db: sqlite3.Connection,
    progress_every: int,
) -> tuple[int, int]:
    """Remove Blob-present SQL hashes using the indexed composite key directly."""
    catalog = list_canonical_catalog(storage, container)
    target_pairs = core._target_pairs()
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
                # API config and Raw wrappers preserve these canonical names, so
                # direct equality is both stricter and lets SQLite use the PK.
                delete_batch.append(
                    (
                        str(record["dataset"]),
                        str(record["operation"]),
                        observed_hash,
                    )
                )
                if len(delete_batch) >= 10_000:
                    db.executemany(
                        "DELETE FROM pending WHERE dataset=? AND operation=? AND payload_hash=?",
                        delete_batch,
                    )
                    delete_batch.clear()
        if delete_batch:
            db.executemany(
                "DELETE FROM pending WHERE dataset=? AND operation=? AND payload_hash=?",
                delete_batch,
            )
        db.commit()
        if decoded_count != int(item["record_count"]):
            raise RuntimeError(
                f"Raw Blob record_count mismatch path={path} decoded={decoded_count} "
                f"metadata={item['record_count']}"
            )
        decoded_records += decoded_count
        if (
            blob_index == 1
            or blob_index % progress_every == 0
            or blob_index == len(targets)
        ):
            pending = int(db.execute("SELECT count(*) FROM pending").fetchone()[0])
            print(
                "SQL/BLOB PARITY PROGRESS "
                f"blobs={blob_index}/{len(targets)} decoded={decoded_records} pending={pending}"
            )
    return len(targets), decoded_records


def main() -> None:
    core.scan_blob_and_remove_preserved = scan_blob_and_remove_preserved
    core.main()


if __name__ == "__main__":
    main()
