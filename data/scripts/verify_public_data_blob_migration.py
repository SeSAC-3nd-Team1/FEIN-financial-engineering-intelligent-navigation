"""Validate legacy raw migration counts, blob sizes, and SHA-256 checksums."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import random

from sqlalchemy import text

from db.connection import build_engine
from storage import BlobStorage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deep", action="store_true", help="Download and hash every migrated blob."
    )
    parser.add_argument("--samples-per-dataset", type=int, default=2)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Report incomplete counts without failing during an active migration.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    engine = build_engine()
    storage = BlobStorage.from_env()
    with engine.connect() as connection:
        source = dict(
            connection.execute(
                text(
                    "SELECT dataset, count(*) FROM raw.public_data_record "
                    "GROUP BY dataset ORDER BY dataset"
                )
            ).all()
        )
        migrated = dict(
            connection.execute(
                text(
                    "SELECT dataset, sum(migrated_row_count) "
                    "FROM raw.public_data_migration_manifest "
                    "WHERE status='complete' GROUP BY dataset ORDER BY dataset"
                )
            ).all()
        )
        manifests = list(
            connection.execute(
                text(
                    "SELECT dataset, operation, source_min_id, source_max_id, "
                    "migrated_row_count, container, blob_path, blob_size, "
                    "content_sha256 FROM raw.public_data_migration_manifest "
                    "WHERE status='complete' ORDER BY manifest_id"
                )
            ).mappings()
        )

    failures: list[str] = []
    for dataset, count in source.items():
        actual = int(migrated.get(dataset, 0))
        print(f"COUNT dataset={dataset} source={count} migrated={actual}")
        if count != actual and not args.allow_partial:
            failures.append(f"count mismatch for {dataset}")

    sampled = set()
    by_dataset: dict[str, list] = {}
    for manifest in manifests:
        by_dataset.setdefault(manifest["dataset"], []).append(manifest)
    for values in by_dataset.values():
        sampled.update(
            item["blob_path"]
            for item in random.sample(
                values, min(args.samples_per_dataset, len(values))
            )
        )

    for index, manifest in enumerate(manifests, 1):
        props = storage.properties(manifest["container"], manifest["blob_path"])
        if props.size != manifest["blob_size"]:
            failures.append(f"size mismatch: {manifest['blob_path']}")
        if props.metadata.get("content_sha256") != manifest["content_sha256"]:
            failures.append(f"metadata checksum mismatch: {manifest['blob_path']}")
        if int(props.metadata.get("record_count", -1)) != manifest[
            "migrated_row_count"
        ]:
            failures.append(f"metadata count mismatch: {manifest['blob_path']}")
        should_download = args.deep or manifest["blob_path"] in sampled
        if should_download:
            client = storage.service_client.get_blob_client(
                manifest["container"], manifest["blob_path"]
            )
            data = client.download_blob(max_concurrency=4).readall()
            if hashlib.sha256(data).hexdigest() != manifest["content_sha256"]:
                failures.append(f"checksum mismatch: {manifest['blob_path']}")
                continue
            rows = [
                json.loads(line)
                for line in gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb")
            ]
            if len(rows) != manifest["migrated_row_count"]:
                failures.append(f"record mismatch: {manifest['blob_path']}")
            for row in rows:
                canonical = json.dumps(
                    row["payload"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                if hashlib.sha256(canonical).hexdigest() != row["payloadHash"]:
                    failures.append(f"payload hash mismatch: {manifest['blob_path']}")
                    break
            if manifest["blob_path"] in sampled and rows:
                sample = rows[len(rows) // 2]
                record_id = sample["legacy"]["recordId"]
                with engine.connect() as connection:
                    source_row = connection.execute(
                        text(
                            "SELECT payload, payload_hash "
                            "FROM raw.public_data_record WHERE record_id=:record_id"
                        ),
                        {"record_id": record_id},
                    ).mappings().one()
                if (
                    source_row["payload"] != sample["payload"]
                    or source_row["payload_hash"] != sample["payloadHash"]
                ):
                    failures.append(
                        f"PostgreSQL sample mismatch: {manifest['blob_path']}"
                    )
        if index % 100 == 0:
            print(f"CHECKED manifests={index}/{len(manifests)}")

    print(
        f"verification complete source={sum(source.values())} "
        f"migrated={sum(migrated.values())} manifests={len(manifests)} "
        f"failures={len(failures)}"
    )
    if failures:
        raise RuntimeError("; ".join(failures[:20]))


if __name__ == "__main__":
    main()
