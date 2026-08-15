"""Delete legacy Raw blobs only after the monthly repartition has been verified.

Safety rules:
- delete only the 525 historical `migration/data-go-kr/` blobs;
- delete only the one known legacy daily E2E blob;
- require the canonical monthly replacement for that daily blob to exist;
- abort if the historical migration blob count is not exactly 525;
- never delete canonical YYYY/MM blobs.
"""

from __future__ import annotations

import os

from storage.blob import BlobStorage


MIGRATION_PREFIX = "migration/data-go-kr/"
EXPECTED_MIGRATION_BLOBS = 525
LEGACY_DAILY_PATH = (
    "data-go-kr/stock_price/operation=getstockpriceinfo/"
    "year=2026/month=08/day=13/"
    "page-00000001-2e4db9d993d5852441f493e36dc4b045dfc54213f24fb8042ee8b6941b0c3a51.jsonl.gz"
)
LEGACY_MONTHLY_REPLACEMENT = (
    "data-go-kr/stock_price/operation=getstockpriceinfo/"
    "year=2026/month=08/"
    "2e4db9d993d5852441f493e36dc4b045dfc54213f24fb8042ee8b6941b0c3a51.jsonl.gz"
)


def main() -> None:
    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    container_client = storage.service_client.get_container_client(container)

    migration_paths = sorted(
        path
        for path in storage.list_paths(container, prefix=MIGRATION_PREFIX)
        if path.endswith(".jsonl.gz")
    )
    if len(migration_paths) != EXPECTED_MIGRATION_BLOBS:
        raise RuntimeError(
            "Refusing cleanup: expected "
            f"{EXPECTED_MIGRATION_BLOBS} migration blobs, found {len(migration_paths)}"
        )

    if not storage.exists(container, LEGACY_DAILY_PATH):
        raise RuntimeError(f"Refusing cleanup: legacy daily blob missing: {LEGACY_DAILY_PATH}")
    if not storage.exists(container, LEGACY_MONTHLY_REPLACEMENT):
        raise RuntimeError(
            "Refusing cleanup: canonical monthly replacement missing: "
            f"{LEGACY_MONTHLY_REPLACEMENT}"
        )

    print(
        "CLEANUP PRECHECK OK "
        f"migration_blobs={len(migration_paths)} legacy_daily=1 monthly_replacement=1"
    )

    deleted = 0
    for index, path in enumerate(migration_paths, start=1):
        container_client.delete_blob(path, delete_snapshots="include")
        deleted += 1
        if index % 50 == 0 or index == len(migration_paths):
            print(f"DELETE migration {index}/{len(migration_paths)}")

    container_client.delete_blob(LEGACY_DAILY_PATH, delete_snapshots="include")
    deleted += 1
    print(f"DELETE legacy_daily path={LEGACY_DAILY_PATH}")

    remaining_migration = storage.list_paths(container, prefix=MIGRATION_PREFIX)
    if remaining_migration:
        raise RuntimeError(
            f"Cleanup verification failed: {len(remaining_migration)} migration blobs remain"
        )
    if storage.exists(container, LEGACY_DAILY_PATH):
        raise RuntimeError("Cleanup verification failed: legacy daily blob still exists")
    if not storage.exists(container, LEGACY_MONTHLY_REPLACEMENT):
        raise RuntimeError("Cleanup verification failed: monthly replacement disappeared")

    canonical_paths = storage.list_paths(container, prefix="data-go-kr/")
    legacy_day_paths = [path for path in canonical_paths if "/day=" in path]
    if legacy_day_paths:
        raise RuntimeError(
            f"Cleanup verification failed: {len(legacy_day_paths)} day-partition blobs remain"
        )

    print(
        "CLEANUP COMPLETE "
        f"deleted={deleted} migration_remaining=0 day_partition_remaining=0 "
        f"canonical_blobs={len(canonical_paths)}"
    )


if __name__ == "__main__":
    main()
