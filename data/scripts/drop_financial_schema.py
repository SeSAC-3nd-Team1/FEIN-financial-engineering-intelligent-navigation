"""Drop the legacy financial PostgreSQL schema after explicit safety checks.

This is a one-off destructive reset tool used before redesigning the financial
PostgreSQL layer from Azure Raw Blob. It intentionally does NOT run as an Alembic
migration so a normal ``alembic upgrade`` can never unexpectedly delete data.

The public membership schema is protected. The command refuses to drop ``raw``
when any raw table still contains rows or when an object outside ``raw`` depends
on a raw relation. ``DROP SCHEMA raw CASCADE`` is executed only after those gates
pass, so CASCADE can only remove objects contained inside the raw schema.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

from db.connection import build_engine


RAW_SCHEMA = "raw"
MEMBERSHIP_TABLES = (
    "public.users",
    "public.terms",
    "public.user_agreements",
)
ALEMBIC_TABLE = "public.alembic_version"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Drop the legacy financial raw schema while preserving membership tables."
        )
    )
    parser.add_argument(
        "--confirm-drop-raw-schema",
        action="store_true",
        help="Required destructive confirmation. Without it the command is read-only.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Optional dotenv file. Existing environment variables take precedence.",
    )
    return parser.parse_args()


def table_exists(connection, fullname: str) -> bool:
    return bool(
        connection.scalar(
            text("SELECT to_regclass(:name) IS NOT NULL"), {"name": fullname}
        )
    )


def membership_counts(connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for fullname in MEMBERSHIP_TABLES:
        if not table_exists(connection, fullname):
            raise RuntimeError(f"Protected membership table is missing: {fullname}")
        counts[fullname] = int(
            connection.scalar(text(f"SELECT count(*) FROM {fullname}")) or 0
        )
    return counts


def alembic_version(connection) -> str | None:
    if not table_exists(connection, ALEMBIC_TABLE):
        raise RuntimeError("Protected Alembic version table is missing")
    return connection.scalar(text("SELECT version_num FROM public.alembic_version LIMIT 1"))


def raw_relations(connection) -> list[tuple[str, str]]:
    rows = connection.execute(
        text(
            """
            SELECT c.relname, c.relkind
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema
              AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
            ORDER BY c.relkind, c.relname
            """
        ),
        {"schema": RAW_SCHEMA},
    )
    return [(str(row.relname), str(row.relkind)) for row in rows]


def nonempty_raw_tables(connection, relations: list[tuple[str, str]]) -> list[str]:
    quote = connection.dialect.identifier_preparer.quote
    nonempty: list[str] = []
    for relation_name, relation_kind in relations:
        if relation_kind not in {"r", "p"}:
            continue
        qualified = f"{quote(RAW_SCHEMA)}.{quote(relation_name)}"
        has_row = connection.scalar(text(f"SELECT EXISTS (SELECT 1 FROM {qualified} LIMIT 1)"))
        if has_row:
            nonempty.append(f"{RAW_SCHEMA}.{relation_name}")
    return nonempty


def external_dependencies(connection) -> list[str]:
    dependencies: set[str] = set()

    # Foreign keys defined outside raw that reference a raw table.
    for row in connection.execute(
        text(
            """
            SELECT src_ns.nspname AS dependent_schema,
                   src.relname AS dependent_name,
                   con.conname AS dependency_name
            FROM pg_constraint AS con
            JOIN pg_class AS src ON src.oid = con.conrelid
            JOIN pg_namespace AS src_ns ON src_ns.oid = src.relnamespace
            JOIN pg_class AS ref ON ref.oid = con.confrelid
            JOIN pg_namespace AS ref_ns ON ref_ns.oid = ref.relnamespace
            WHERE con.contype = 'f'
              AND ref_ns.nspname = :schema
              AND src_ns.nspname <> :schema
            ORDER BY 1, 2, 3
            """
        ),
        {"schema": RAW_SCHEMA},
    ):
        dependencies.add(
            f"FK {row.dependent_schema}.{row.dependent_name}.{row.dependency_name}"
        )

    # Views/materialized views outside raw that depend on a raw relation.
    for row in connection.execute(
        text(
            """
            SELECT DISTINCT dep_ns.nspname AS dependent_schema,
                            dep.relname AS dependent_name,
                            dep.relkind AS dependent_kind
            FROM pg_depend AS d
            JOIN pg_rewrite AS rw ON rw.oid = d.objid
            JOIN pg_class AS dep ON dep.oid = rw.ev_class
            JOIN pg_namespace AS dep_ns ON dep_ns.oid = dep.relnamespace
            JOIN pg_class AS ref ON ref.oid = d.refobjid
            JOIN pg_namespace AS ref_ns ON ref_ns.oid = ref.relnamespace
            WHERE ref_ns.nspname = :schema
              AND dep_ns.nspname <> :schema
              AND dep.relkind IN ('v', 'm')
            ORDER BY 1, 2
            """
        ),
        {"schema": RAW_SCHEMA},
    ):
        kind = "MATERIALIZED VIEW" if row.dependent_kind == "m" else "VIEW"
        dependencies.add(f"{kind} {row.dependent_schema}.{row.dependent_name}")

    # SQL functions outside raw with catalog dependencies on raw relations.
    for row in connection.execute(
        text(
            """
            SELECT DISTINCT proc_ns.nspname AS dependent_schema,
                            proc.proname AS dependent_name
            FROM pg_depend AS d
            JOIN pg_proc AS proc ON proc.oid = d.objid
            JOIN pg_namespace AS proc_ns ON proc_ns.oid = proc.pronamespace
            JOIN pg_class AS ref ON ref.oid = d.refobjid
            JOIN pg_namespace AS ref_ns ON ref_ns.oid = ref.relnamespace
            WHERE ref_ns.nspname = :schema
              AND proc_ns.nspname <> :schema
            ORDER BY 1, 2
            """
        ),
        {"schema": RAW_SCHEMA},
    ):
        dependencies.add(f"FUNCTION {row.dependent_schema}.{row.dependent_name}")

    return sorted(dependencies)


def main() -> None:
    args = parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)

    engine = build_engine()

    with engine.connect() as connection:
        protected_before = membership_counts(connection)
        version_before = alembic_version(connection)
        schema_exists = bool(
            connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = :schema)"),
                {"schema": RAW_SCHEMA},
            )
        )
        if not schema_exists:
            print(
                "FINANCIAL SCHEMA ALREADY ABSENT "
                f"schema={RAW_SCHEMA} membership_preserved={protected_before} "
                f"alembic_version={version_before}"
            )
            return

        relations = raw_relations(connection)
        nonempty = nonempty_raw_tables(connection, relations)
        dependencies = external_dependencies(connection)

    print(
        "FINANCIAL SCHEMA DROP PREFLIGHT "
        f"schema={RAW_SCHEMA} relations={len(relations)} "
        f"nonempty_tables={nonempty} external_dependencies={dependencies} "
        f"membership={protected_before} alembic_version={version_before}"
    )

    if nonempty:
        raise RuntimeError(
            "Refusing schema drop because raw tables still contain rows: "
            + ", ".join(nonempty)
        )
    if dependencies:
        raise RuntimeError(
            "Refusing schema drop because objects outside raw depend on it: "
            + "; ".join(dependencies)
        )
    if not args.confirm_drop_raw_schema:
        print("DRY RUN: raw schema was not dropped")
        return

    with engine.begin() as connection:
        # Recheck protected state and destructive gates inside the same transaction.
        if membership_counts(connection) != protected_before:
            raise RuntimeError("Membership data changed during preflight; refusing DROP")
        if alembic_version(connection) != version_before:
            raise RuntimeError("Alembic version changed during preflight; refusing DROP")

        relations_now = raw_relations(connection)
        nonempty_now = nonempty_raw_tables(connection, relations_now)
        dependencies_now = external_dependencies(connection)
        if nonempty_now:
            raise RuntimeError(
                "Raw data appeared during preflight; refusing DROP: "
                + ", ".join(nonempty_now)
            )
        if dependencies_now:
            raise RuntimeError(
                "External dependency appeared during preflight; refusing DROP: "
                + "; ".join(dependencies_now)
            )

        connection.execute(text("DROP SCHEMA raw CASCADE"))

        if connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'raw')")
        ):
            raise RuntimeError("raw schema still exists after DROP")
        protected_after = membership_counts(connection)
        version_after = alembic_version(connection)
        if protected_after != protected_before:
            raise RuntimeError(
                f"Membership counts changed: before={protected_before} after={protected_after}"
            )
        if version_after != version_before:
            raise RuntimeError(
                f"Alembic version changed: before={version_before} after={version_after}"
            )

    print(
        "FINANCIAL SCHEMA DROP COMPLETE "
        f"schema={RAW_SCHEMA} removed_relations={len(relations)} "
        f"membership_preserved={protected_before} alembic_version={version_before}"
    )


if __name__ == "__main__":
    main()
