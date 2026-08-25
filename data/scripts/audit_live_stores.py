"""실제 Azure Blob과 PostgreSQL의 메타데이터·집계값을 안전하게 감사한다.

두 저장소는 서로 독립적으로 검사한다. 인증정보, DB endpoint, 사용자 row는 보고서에
기록하지 않으며 Blob metadata와 PostgreSQL aggregate만 READ ONLY로 조회한다.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from azure.core.exceptions import HttpResponseError
from azure.identity import AzureCliCredential
from azure.storage.blob import BlobServiceClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"
MARKDOWN_PATH = REPORT_DIR / "AZURE_LIVE_AUDIT.md"
JSON_PATH = REPORT_DIR / "azure_live_audit.json"

DATE_COLUMNS_PRIORITY = (
    "trade_date", "snapshot_date", "effective_from", "as_of", "base_date",
    "created_at", "updated_at", "requested_at", "executed_at",
)
SERVICE_TABLES = {
    "users", "terms", "user_agreements", "virtual_accounts", "investment_onboardings",
    "positions", "portfolio_snapshots", "orders", "executions", "cash_ledger",
    "strategies", "strategy_target_weights", "rebalancing_decisions",
}
KRX_SERVING_TABLES = {"market_stocks", "market_stock_prices", "market_indices"}


def _human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() == "true"


def _issue(stage: str, exc: BaseException, reason: str) -> dict[str, str]:
    """예외 본문 대신 고정된 원인 코드만 남겨 endpoint나 credential 노출을 막는다."""

    return {"stage": stage, "error_type": type(exc).__name__, "reason": reason}


def _logical_prefix(container_name: str, blob_name: str) -> str:
    """실제 container/path 배치에 맞춰 layer와 source/dataset 수준까지 집계한다."""

    parts = [part for part in blob_name.split("/") if part]
    if not parts:
        return "(root)"
    layer = container_name.lower()
    if parts[0].lower() == layer and layer in {"raw", "processed", "features"}:
        parts = parts[1:]
    elif parts[0].lower() in {"raw", "processed", "features"}:
        layer = parts.pop(0).lower()
    if not parts:
        return layer if layer in {"raw", "processed", "features"} else "(root)"
    if layer == "raw" and len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    if layer in {"processed", "features"}:
        return parts[0]
    return parts[0]


def _blob_base() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "diagnostics": {
            "azure_login_ok": _env_flag("AZURE_LOGIN_OK"),
            "token_acquisition_ok": False,
            "storage_account_reachable": False,
            "blob_data_plane_authorized": False,
            "audit_ok": False,
        },
        "container_count": 0,
        "blob_count": 0,
        "bytes": 0,
        "containers": [],
        "issues": [],
    }


def audit_blob() -> dict[str, Any]:
    """Azure CLI OIDC session으로 Blob data-plane metadata를 전수 집계한다."""

    result = _blob_base()
    account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "").strip()
    if not account_name:
        result["issues"].append(
            {"stage": "configuration", "error_type": "MissingSetting", "reason": "storage_account_not_configured"}
        )
        return result

    account_host = f"{account_name}.blob.core.windows.net"
    try:
        socket.getaddrinfo(account_host, 443, type=socket.SOCK_STREAM)
        with socket.create_connection((account_host, 443), timeout=5):
            pass
        result["diagnostics"]["storage_account_reachable"] = True
    except (OSError, TimeoutError) as exc:
        result["issues"].append(_issue("storage_reachability", exc, "storage_network_unreachable"))

    # azure/login이 만든 Azure CLI cache만 사용해 credential source를 모호하게 만들지 않는다.
    credential = AzureCliCredential(process_timeout=10)
    try:
        credential.get_token("https://storage.azure.com/.default")
        result["diagnostics"]["token_acquisition_ok"] = True
        result["diagnostics"]["azure_login_ok"] = True
    except Exception as exc:  # noqa: BLE001 - 다른 저장소 감사가 계속되어야 한다.
        result["issues"].append(_issue("token_acquisition", exc, "azure_cli_token_unavailable"))
        return result

    service = BlobServiceClient(
        account_url=f"https://{account_host}", credential=credential,
        connection_timeout=10, read_timeout=30,
    )
    try:
        container_items = list(service.list_containers())
        result["diagnostics"]["storage_account_reachable"] = True
        result["diagnostics"]["blob_data_plane_authorized"] = True
        result["issues"] = [
            item for item in result["issues"] if item["stage"] != "storage_reachability"
        ]
    except HttpResponseError as exc:
        result["diagnostics"]["storage_account_reachable"] = True
        reason = "blob_data_plane_forbidden" if exc.status_code in {401, 403} else "blob_data_plane_request_failed"
        result["issues"].append(_issue("blob_data_plane", exc, reason))
        return result
    except Exception as exc:  # noqa: BLE001 - 민감한 SDK 예외 본문은 저장하지 않는다.
        result["issues"].append(_issue("blob_data_plane", exc, "blob_data_plane_request_failed"))
        return result

    containers: list[dict[str, Any]] = []
    for container_item in container_items:
        name = str(container_item["name"])
        client = service.get_container_client(name)
        total_bytes = 0
        blob_count = 0
        newest: datetime | None = None
        prefixes: Counter[str] = Counter()
        prefix_bytes: defaultdict[str, int] = defaultdict(int)
        try:
            for blob in client.list_blobs():
                blob_count += 1
                size = int(blob.size or 0)
                total_bytes += size
                modified = blob.last_modified
                if modified and (newest is None or modified > newest):
                    newest = modified
                prefix = _logical_prefix(name, blob.name)
                prefixes[prefix] += 1
                prefix_bytes[prefix] += size
        except Exception as exc:  # noqa: BLE001 - 가능한 container 결과는 계속 보존한다.
            result["issues"].append(_issue("container_listing", exc, "container_metadata_unavailable"))
            containers.append({"name": name, "status": "error", "error_type": type(exc).__name__})
            continue
        containers.append(
            {
                "name": name, "status": "ok", "blob_count": blob_count, "bytes": total_bytes,
                "latest_modified": newest.isoformat() if newest else None,
                "prefixes": [
                    {"name": prefix, "blob_count": count, "bytes": prefix_bytes[prefix]}
                    for prefix, count in prefixes.most_common()
                ],
            }
        )

    successful = [item for item in containers if item["status"] == "ok"]
    result.update(
        {
            "status": "ok" if len(successful) == len(containers) else "partial",
            "container_count": len(containers),
            "blob_count": sum(item["blob_count"] for item in successful),
            "bytes": sum(item["bytes"] for item in successful),
            "containers": containers,
        }
    )
    result["diagnostics"]["audit_ok"] = len(successful) == len(containers)
    return result


def _postgres_base() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "diagnostics": {
            "database_url_configured": bool(os.getenv("DATABASE_URL", "").strip()),
            "dns_ok": False,
            "tcp_5432_ok": False,
            "postgres_connect_ok": False,
            "audit_ok": False,
        },
        "table_count": 0,
        "tables": [],
        "issues": [],
    }


def _normalized_database_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def _database_endpoint(database_url: str) -> tuple[str, int]:
    """연결 문자열을 내부 진단에만 사용하고 host/IP/user는 반환 결과에 넣지 않는다."""

    options = conninfo_to_dict(_normalized_database_url(database_url))
    host = str(options.get("host") or "").split(",", 1)[0].strip()
    port_text = str(options.get("port") or "5432").split(",", 1)[0]
    if not host:
        raise ValueError("database host is missing")
    return host, int(port_text)


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
    """DNS, TCP, PostgreSQL handshake와 실제 aggregate 조회를 단계별로 진단한다."""

    result = _postgres_base()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        result["issues"].append(
            {"stage": "configuration", "error_type": "MissingSetting", "reason": "database_url_not_configured"}
        )
        return result

    try:
        host, port = _database_endpoint(database_url)
    except Exception as exc:  # noqa: BLE001 - URL 본문을 보고서에 포함하지 않는다.
        result["issues"].append(_issue("database_url_parse", exc, "database_url_invalid"))
        return result
    if port != 5432:
        result["issues"].append(
            {"stage": "tcp_5432", "error_type": "InvalidPort", "reason": "database_port_not_5432"}
        )
        return result

    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        result["diagnostics"]["dns_ok"] = True
    except OSError as exc:
        result["issues"].append(_issue("dns", exc, "database_dns_resolution_failed"))
        return result

    try:
        with socket.create_connection((host, port), timeout=5):
            pass
        result["diagnostics"]["tcp_5432_ok"] = True
    except (OSError, TimeoutError) as exc:
        result["issues"].append(_issue("tcp_5432", exc, "database_tcp_connection_failed"))
        return result

    tables: list[dict[str, Any]] = []
    try:
        with psycopg.connect(_normalized_database_url(database_url), connect_timeout=15) as connection:
            result["diagnostics"]["postgres_connect_ok"] = True
            connection.autocommit = True
            with connection.cursor() as cur:
                cur.execute("SET default_transaction_read_only = on")
                cur.execute("SET statement_timeout = '300s'")
                cur.execute(
                    """
                    SELECT table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_type = 'BASE TABLE'
                      AND table_schema NOT IN ('pg_catalog', 'information_schema')
                      AND table_schema NOT LIKE 'pg_%'
                    ORDER BY table_schema, table_name
                    """
                )
                table_names = cur.fetchall()

                for schema, table in table_names:
                    try:
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
                                    c=sql.Identifier(date_column), s=sql.Identifier(schema),
                                    t=sql.Identifier(table),
                                )
                            )
                            min_value, max_value = cur.fetchone()
                        tables.append(
                            {
                                "schema": schema, "table": table, "status": "ok",
                                "row_count": row_count, "date_column": date_column,
                                "min_date": min_value.isoformat() if min_value is not None else None,
                                "max_date": max_value.isoformat() if max_value is not None else None,
                            }
                        )
                    except Exception as exc:  # noqa: BLE001 - 다른 table COUNT를 계속 수행한다.
                        tables.append(
                            {"schema": schema, "table": table, "status": "error", "error_type": type(exc).__name__}
                        )
                        result["issues"].append(_issue("table_aggregate", exc, "table_aggregate_unavailable"))
    except Exception as exc:  # noqa: BLE001 - host/user가 포함될 수 있는 원문은 버린다.
        result["issues"].append(_issue("postgres_connect", exc, "postgres_handshake_failed"))
        return result

    failed_tables = [item for item in tables if item["status"] != "ok"]
    result.update({"status": "ok" if not failed_tables else "partial", "table_count": len(tables), "tables": tables})
    result["diagnostics"]["audit_ok"] = not failed_tables
    return result


def _yes_no(value: bool) -> str:
    return "OK" if value else "FAIL"


def _render_blob(lines: list[str], blob: dict[str, Any]) -> None:
    diagnostics = blob["diagnostics"]
    lines.extend(
        [
            "## 1. Azure Blob Storage", "", "| Diagnostic | Result |", "|---|---|",
            *[f"| `{name}` | **{_yes_no(value)}** |" for name, value in diagnostics.items()], "",
            f"- 연결 상태: **{blob['status'].upper()}**",
            f"- Container 수: **{blob['container_count']:,}**",
            f"- Blob 수: **{blob['blob_count']:,}**",
            f"- 총 용량: **{_human_bytes(blob['bytes'])}**",
        ]
    )
    if not blob["containers"]:
        lines.extend(["", "- Container/prefix 현황: 확인 불가"])
        return
    lines.extend(["", "| Container | Blobs | Size | Latest modified |", "|---|---:|---:|---|"])
    for container in blob["containers"]:
        if container["status"] != "ok":
            lines.append(f"| `{container['name']}` | 확인 불가 | 확인 불가 | 확인 불가 |")
            continue
        lines.append(
            f"| `{container['name']}` | {container['blob_count']:,} | "
            f"{_human_bytes(container['bytes'])} | {container['latest_modified'] or '-'} |"
        )
        if container["prefixes"]:
            lines.extend(["", f"### `{container['name']}` logical prefixes", "", "| Prefix | Blobs | Size |", "|---|---:|---:|"])
            for prefix in container["prefixes"]:
                lines.append(f"| `{prefix['name']}` | {prefix['blob_count']:,} | {_human_bytes(prefix['bytes'])} |")


def _render_postgres(lines: list[str], postgres: dict[str, Any]) -> None:
    diagnostics = postgres["diagnostics"]
    lines.extend(
        [
            "", "## 2. PostgreSQL", "", "| Diagnostic | Result |", "|---|---|",
            *[f"| `{name}` | **{_yes_no(value)}** |" for name, value in diagnostics.items()], "",
            f"- 연결 상태: **{postgres['status'].upper()}**",
            f"- 사용자 schema BASE TABLE 수: **{postgres['table_count']:,}**",
        ]
    )
    if not postgres["tables"]:
        lines.extend(["", "- Table row count/날짜 범위: 확인 불가"])
        return
    lines.extend(["", "| Schema | Table | Rows | Date column | Min | Max |", "|---|---|---:|---|---|---|"])
    for table in postgres["tables"]:
        if table["status"] != "ok":
            lines.append(f"| `{table['schema']}` | `{table['table']}` | 확인 불가 | - | - | - |")
            continue
        lines.append(
            f"| `{table['schema']}` | `{table['table']}` | {table['row_count']:,} | "
            f"`{table['date_column'] or '-'}` | {table['min_date'] or '-'} | {table['max_date'] or '-'} |"
        )


def _blob_layer_rows(blob: dict[str, Any]) -> dict[str, tuple[int, int]]:
    return {
        item["name"].lower(): (item["blob_count"], item["bytes"])
        for item in blob["containers"]
        if item["status"] == "ok" and item["name"].lower() in {"raw", "processed", "features"}
    }


def _render_roles(lines: list[str], result: dict[str, Any]) -> None:
    lines.extend(["", "## 3. 데이터 역할 정리", ""])
    blob = result["blob"]
    if blob["diagnostics"]["audit_ok"]:
        layers = _blob_layer_rows(blob)
        for layer, label in (("raw", "모델 Raw"), ("processed", "Processed"), ("features", "Features")):
            if layer in layers:
                count, size = layers[layer]
                lines.append(f"- Blob {label}: {count:,} blobs / {_human_bytes(size)}")
            else:
                lines.append(f"- Blob {label}: 실제 container에서 확인되지 않음")
    else:
        lines.append("- Blob 모델 Raw/Processed/Features: 확인 불가")

    postgres = result["postgres"]
    if postgres["diagnostics"]["audit_ok"]:
        actual = {item["table"]: item for item in postgres["tables"] if item["status"] == "ok"}
        service = [name for name in sorted(SERVICE_TABLES) if name in actual]
        krx = [name for name in sorted(KRX_SERVING_TABLES) if name in actual]
        lines.append(f"- PostgreSQL 사용자/계좌/거래: {', '.join(service) if service else '실제 table 없음'}")
        lines.append(f"- PostgreSQL KRX 서비스 조회: {', '.join(krx) if krx else '실제 table 없음'}")
    else:
        lines.append("- PostgreSQL 사용자/계좌/거래 및 KRX 서비스 조회: 확인 불가")


def _render_issues(lines: list[str], result: dict[str, Any]) -> None:
    lines.extend(["", "## 4. 발견된 문제", ""])
    issues = [("Blob", item) for item in result["blob"]["issues"]]
    issues.extend(("PostgreSQL", item) for item in result["postgres"]["issues"])
    if not issues:
        lines.append("- 발견된 연결·권한·조회 문제가 없습니다.")
        return
    for store, item in issues:
        lines.append(f"- {store} `{item['stage']}`: `{item['error_type']}` / `{item['reason']}`")


def render_markdown(result: dict[str, Any]) -> str:
    """민감정보 없이 운영자가 바로 판단할 수 있는 순서로 Markdown을 만든다."""

    lines = [
        "# Azure Live Storage Audit", "",
        f"> Generated at `{result['generated_at']}` from live READ ONLY metadata/aggregate queries.",
        "> Secrets, DB endpoint/user/IP, tokens, SAS, connection strings, and application rows are not included.", "",
    ]
    _render_blob(lines, result["blob"])
    _render_postgres(lines, result["postgres"])
    _render_roles(lines, result)
    _render_issues(lines, result)
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    logging.getLogger("azure.identity").setLevel(logging.ERROR)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "blob": audit_blob(),
        "postgres": audit_postgres(),
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    MARKDOWN_PATH.write_text(render_markdown(result), encoding="utf-8")
    print(MARKDOWN_PATH.read_text(encoding="utf-8"))
    if not result["blob"]["diagnostics"]["audit_ok"] or not result["postgres"]["diagnostics"]["audit_ok"]:
        raise SystemExit("One or more live store audits failed; see the sanitized report")


if __name__ == "__main__":
    main()
