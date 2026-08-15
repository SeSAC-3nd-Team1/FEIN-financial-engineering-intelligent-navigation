"""Read-only DROP-readiness audit for ``raw.public_data_record``.

This script never changes PostgreSQL. It reports relation size, row estimate,
database-level dependencies, migration evidence, and Raw Blob catalog status so a
human can decide whether the legacy JSONB landing table is safe to remove later.
"""

from __future__ import annotations

import argparse

from sqlalchemy import text

from db.connection import build_engine


TARGET = "raw.public_data_record"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--exact-count",
        action="store_true",
        help="Run COUNT(*) on the ~14GB legacy table; slower than catalog estimate.",
    )
    return parser.parse_args()


def scalar(connection, sql: str):
    return connection.execute(text(sql)).scalar_one()


def main() -> None:
    args = parse_args()
    engine = build_engine()
    with engine.connect() as connection:
        exists = scalar(
            connection,
            "SELECT to_regclass('raw.public_data_record') IS NOT NULL",
        )
        if not exists:
            print("LEGACY RAW TABLE ABSENT raw.public_data_record")
            return

        size_bytes = scalar(
            connection,
            "SELECT pg_total_relation_size('raw.public_data_record')",
        )
        row_estimate = scalar(
            connection,
            """
            SELECT c.reltuples::bigint
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'raw' AND c.relname = 'public_data_record'
            """,
        )
        exact_count = None
        if args.exact_count:
            exact_count = scalar(connection, f"SELECT count(*) FROM {TARGET}")

        fk_dependencies = list(
            connection.execute(
                text(
                    """
                    SELECT conrelid::regclass::text AS referencing_relation, conname
                    FROM pg_constraint
                    WHERE contype = 'f'
                      AND confrelid = 'raw.public_data_record'::regclass
                    ORDER BY 1, 2
                    """
                )
            )
        )
        view_dependencies = list(
            connection.execute(
                text(
                    """
                    SELECT DISTINCT view_schema, view_name
                    FROM information_schema.view_table_usage
                    WHERE table_schema = 'raw'
                      AND table_name = 'public_data_record'
                    ORDER BY 1, 2
                    """
                )
            )
        )
        indexes = scalar(
            connection,
            """
            SELECT count(*)
            FROM pg_indexes
            WHERE schemaname = 'raw' AND tablename = 'public_data_record'
            """,
        )
        manifest_complete = scalar(
            connection,
            """
            SELECT count(*)
            FROM raw.public_data_migration_manifest
            WHERE source_table = 'raw.public_data_record' AND status = 'complete'
            """,
        )
        data_object_available = scalar(
            connection,
            "SELECT count(*) FROM raw.data_object WHERE status = 'available'",
        )
        data_object_deleted = scalar(
            connection,
            "SELECT count(*) FROM raw.data_object WHERE status = 'deleted'",
        )

    print(
        "LEGACY RAW AUDIT "
        f"table={TARGET} size_bytes={size_bytes} row_estimate={row_estimate} "
        f"exact_count={exact_count if exact_count is not None else 'skipped'} "
        f"indexes={indexes}"
    )
    print(
        "MIGRATION EVIDENCE "
        f"complete_manifests={manifest_complete} "
        f"data_object_available={data_object_available} "
        f"data_object_deleted={data_object_deleted}"
    )
    for relation, constraint in fk_dependencies:
        print(f"FK DEPENDENCY relation={relation} constraint={constraint}")
    for schema, view in view_dependencies:
        print(f"VIEW DEPENDENCY view={schema}.{view}")

    blockers = len(fk_dependencies) + len(view_dependencies)
    if blockers:
        print(f"DROP READINESS blocked database_dependencies={blockers}")
    else:
        print(
            "DROP READINESS database_dependencies=0; "
            "still require code-reference review, Blob/catalog validation, backup/PITR "
            "confirmation, and explicit human approval before DROP"
        )


if __name__ == "__main__":
    main()
