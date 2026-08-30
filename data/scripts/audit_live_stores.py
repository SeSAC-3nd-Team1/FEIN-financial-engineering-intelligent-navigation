"""Audit live Azure Blob metadata and PostgreSQL aggregates safely.

Each store is audited independently. If Blob authentication is unavailable, the
PostgreSQL audit still completes and the report records only the error type.
No application row values, credentials, connection strings, hosts, or users are printed.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import psycopg
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from psycopg import sql

REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"
MARKDOWN_PATH = REPORT_DIR / "AZURE_LIVE_AUDIT.md"
JSON_PATH = REPORT_DIR / "azure_live_audit.json"

DATE_COLUMNS_PRIORITY = (
    "trade_date",
    "snapshot_date",
    "effective_from",
    "as_of",
    "base_date",
    "created_at",
    "updated_at",
    "requested_at",
    "executed_at",
)


def _human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def _prefix(blob_name: str) -> str:
    parts = [part for part in blob_name.split("/") if part]
    if not parts:
        return "(root)"
    first = parts[0]
    if first in {"raw", "processed", "features"} and len(parts) > 1:
        return parts[1]
    return first


def _safe(name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        payload = fn()
        return {"status": "ok", **payload}
    except Exception as exc:  # noqa: BLE001 - audit must continue for the other store
        return {
            "status": "error",
            "store": name,
            "error_type": type(exc).__name__,
        }


def audit_blob() -> dict[str, Any]:
    account_name = os.environ["AZURE_STORAGE_ACCOUNT_NAME"]
    account_url = f"https://{account_name}.blob.core.windows.net"
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    service = BlobServiceClient(account_url=account_url, credential=credential)

    containers: list[dict[str, Any]] = []
    for container_item in service.list_containers():
        name = container_item["name"]
        client = service.get_container_client(name)
        total_bytes = 0
        blob_count = 0
        newest: datetime | None = None
        prefixes: Counter[str] = Counter()
        prefix_bytes: defaultdict[str, int] = defaultdict(int)
        samples: defaultdict[str, list[str]] = defaultdict(list)

        for blob in client.list_blobs():
            blob_count += 1
            size = int(blob.size or 0)
            total_bytes += size
            modified = blob.last_modified
            if modified and (newest is None or modified > newest):
                newest = modified
            prefix = _prefix(blob.name)
            prefixes[prefix] += 1
            prefix_bytes[prefix] += size
            if len(samples[prefix]) < 1:
                samples[prefix].append(blob.name)

        containers.append(
            {
                "name": name,
                "blob_count": blob_count,
                "bytes": total_bytes,
                "latest_modified": newest.isoformat() if newest else None,
                "prefixes": [
                    {
                        "name": prefix,
                        "blob_count": count,
                        "bytes": prefix_bytes[prefix],
                        "samples": samples[prefix],
                    }
                    for prefix, count in prefixes.most_common()
                ],
            }
        )

    return {
        "account_name": account_name,
        "container_count": len(containers),
        "blob_count": sum(item["blob_count"] for item in containers),
        "bytes": sum(item["bytes"] for item in containers),
        "containers": containers,
    }


def _candidate_date_column(cur: psycopg.Cursor[Any], schema: str, table: str) -> str | None:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND data_type IN ('date', 'timestamp without time zone', 'timestamp with time zone')
        """,
        (schema, table),
    )
    columns = {row[0] for row in cur.fetchall()}
    return next((column for column in DATE_COLUMNS_PRIORITY if column in columns), None)


def audit_postgres() -> dict[str, Any]:
    database_url = os.environ["DATABASE_URL"]
    tables: list[dict[str, Any]] = []

    with psycopg.connect(database_url, connect_timeout=15) as connection:
        with connection.cursor() as cur:
            cur.execute("SELECT current_database()")
            database_name = cur.fetchone()[0]
            cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
                """
            )
            table_names = cur.fetchall()

            for schema, table in table_names:
                cur.execute(
                    sql.SQL("SELECT count(*) FROM {}.{}").format(
                        sql.Identifier(schema), sql.Identifier(table)
                    )
                )
                row_count = int(cur.fetchone()[0])

                date_column = _candidate_date_column(cur, schema, table)
                min_value = max_value = None
                if date_column:
                    cur.execute(
                        sql.SQL("SELECT min({c}), max({c}) FROM {s}.{t}").format(
                            c=sql.Identifier(date_column),
                            s=sql.Identifier(schema),
                            t=sql.Identifier(table),
                        )
                    )
                    min_value, max_value = cur.fetchone()

                tables.append(
                    {
                        "schema": schema,
                        "table": table,
                        "row_count": row_count,
                        "date_column": date_column,
                        "min_date": min_value.isoformat() if min_value is not None else None,
                        "max_date": max_value.isoformat() if max_value is not None else None,
                    }
                )

    return {
        "database": database_name,
        "table_count": len(tables),
        "tables": tables,
    }


def render_markdown(result: dict[str, Any]) -> str:
    blob = result["blob"]
    postgres = result["postgres"]
    lines = [
        "# Azure Live Storage Audit",
        "",
        f"> Generated at `{result['generated_at']}` from live aggregate/metadata queries.",
        "> No application row values, secrets, connection strings, hosts, or credentials are included.",
        "",
        "## Azure Blob Storage",
        "",
    ]

    if blob["status"] == "ok":
        lines.extend(
            [
                "- Status: **OK**",
                f"- Account: `{blob['account_name']}`",
                f"- Containers: **{blob['container_count']:,}**",
                f"- Blobs: **{blob['blob_count']:,}**",
                f"- Total size: **{_human_bytes(blob['bytes'])}**",
                "",
                "| Container | Blobs | Size | Latest modified |",
                "|---|---:|---:|---|",
            ]
        )
        for container in blob["containers"]:
            lines.append(
                f"| `{container['name']}` | {container['blob_count']:,} | "
                f"{_human_bytes(container['bytes'])} | {container['latest_modified'] or '-'} |"
            )
            if container["prefixes"]:
                lines.extend(
                    [
                        "",
                        f"### `{container['name']}` logical prefixes",
                        "",
                        "| Prefix | Blobs | Size | Example path |",
                        "|---|---:|---:|---|",
                    ]
                )
                for prefix in container["prefixes"]:
                    example = prefix["samples"][0] if prefix["samples"] else "-"
                    lines.append(
                        f"| `{prefix['name']}` | {prefix['blob_count']:,} | "
                        f"{_human_bytes(prefix['bytes'])} | `{example}` |"
                    )
    else:
        lines.extend(
            [
                "- Status: **UNAVAILABLE**",
                f"- Error type: `{blob['error_type']}`",
                "- Blob metadata could not be queried with the current GitHub Actions Azure identity.",
            ]
        )

    lines.extend(["", "## PostgreSQL", ""])
    if postgres["status"] == "ok":
        lines.extend(
            [
                "- Status: **OK**",
                f"- Database: `{postgres['database']}`",
                f"- Base tables: **{postgres['table_count']:,}**",
                "- Counts below are live `COUNT(*)` results.",
                "",
                "| Schema | Table | Rows | Date column | Min | Max |",
                "|---|---|---:|---|---|---|",
            ]
        )
        for table in postgres["tables"]:
            lines.append(
                f"| `{table['schema']}` | `{table['table']}` | {table['row_count']:,} | "
                f"`{table['date_column'] or '-'}` | {table['min_date'] or '-'} | {table['max_date'] or '-'} |"
            )
    else:
        lines.extend(
            [
                "- Status: **UNAVAILABLE**",
                f"- Error type: `{postgres['error_type']}`",
                "- PostgreSQL aggregate metadata could not be queried.",
            ]
        )

    lines.extend(
        [
            "",
            "## Interpretation rule",
            "",
            "- Blob is the canonical object store for data/model pipelines.",
            "- PostgreSQL is the relational service store, including explicitly synchronized service-facing market tables.",
            "- Presence in PostgreSQL does not make a table the canonical model-training source.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "blob": _safe("blob", audit_blob),
        "postgres": _safe("postgres", audit_postgres),
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    MARKDOWN_PATH.write_text(render_markdown(result), encoding="utf-8")
    print(MARKDOWN_PATH.read_text(encoding="utf-8"))

    if result["blob"]["status"] != "ok" and result["postgres"]["status"] != "ok":
        raise SystemExit("Both live store audits failed")


if __name__ == "__main__":
    main()
