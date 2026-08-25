"""Azure live audit의 단계 진단과 민감정보 비노출 계약을 검증한다."""

from contextlib import nullcontext
from datetime import datetime, timezone
import socket
from types import SimpleNamespace

from scripts import audit_live_stores as audit


def test_logical_prefix_uses_actual_source_and_dataset() -> None:
    assert audit._logical_prefix(
        "raw", "data-go-kr/stock_price/operation=getStockPriceInfo/year=2026/file.gz"
    ) == "data-go-kr/stock_price"
    assert audit._logical_prefix("raw", "krx/market_index/operation=kospi_dd_trd/file.gz") == "krx/market_index"
    assert audit._logical_prefix("processed", "stock_price/schema=v1/file.parquet") == "stock_price"
    assert audit._logical_prefix("lake", "raw/ecos/base_rate/file.gz") == "ecos/base_rate"


def test_blob_audit_uses_cli_credential_and_aggregates_metadata(monkeypatch) -> None:
    class FakeCredential:
        def __init__(self, **_kwargs) -> None:
            pass

        def get_token(self, scope: str) -> object:
            assert scope == "https://storage.azure.com/.default"
            return object()

    blobs = [
        SimpleNamespace(
            name="krx/stock_price/operation=stk/file.gz",
            size=10,
            last_modified=datetime(2026, 8, 25, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            name="data-go-kr/stock_master/operation=master/file.gz",
            size=20,
            last_modified=datetime(2026, 8, 24, tzinfo=timezone.utc),
        ),
    ]

    class FakeContainer:
        def list_blobs(self):
            return blobs

    class FakeService:
        def __init__(self, **_kwargs) -> None:
            pass

        def list_containers(self):
            return [{"name": "raw"}]

        def get_container_client(self, name: str) -> FakeContainer:
            assert name == "raw"
            return FakeContainer()

    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_NAME", "account")
    monkeypatch.setattr(audit, "AzureCliCredential", FakeCredential)
    monkeypatch.setattr(audit, "BlobServiceClient", FakeService)
    monkeypatch.setattr(audit.socket, "getaddrinfo", lambda *_args, **_kwargs: [object()])
    monkeypatch.setattr(audit.socket, "create_connection", lambda *_args, **_kwargs: nullcontext())

    result = audit.audit_blob()

    assert result["diagnostics"] == {
        "azure_login_ok": True,
        "token_acquisition_ok": True,
        "storage_account_reachable": True,
        "blob_data_plane_authorized": True,
        "audit_ok": True,
    }
    assert result["blob_count"] == 2
    assert result["bytes"] == 30
    assert [item["name"] for item in result["containers"][0]["prefixes"]] == [
        "krx/stock_price", "data-go-kr/stock_master",
    ]


def test_postgres_dns_failure_is_classified_without_endpoint(monkeypatch) -> None:
    secret_url = "postgresql://hidden_user:hidden_password@hidden-host.example:5432/hidden_db"
    monkeypatch.setenv("DATABASE_URL", secret_url)
    monkeypatch.setattr(audit.socket, "getaddrinfo", lambda *_args, **_kwargs: (_ for _ in ()).throw(socket.gaierror()))

    result = audit.audit_postgres()
    rendered = audit.render_markdown(
        {"generated_at": "2026-08-25T00:00:00+00:00", "blob": audit._blob_base(), "postgres": result}
    )

    assert result["diagnostics"]["database_url_configured"] is True
    assert result["diagnostics"]["dns_ok"] is False
    assert result["issues"] == [{
        "stage": "dns", "error_type": "gaierror", "reason": "database_dns_resolution_failed",
    }]
    for secret in (secret_url, "hidden_user", "hidden_password", "hidden-host.example", "hidden_db"):
        assert secret not in rendered


def test_postgres_tcp_failure_is_distinct_from_handshake(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@db.invalid:5432/app")
    monkeypatch.setattr(audit.socket, "getaddrinfo", lambda *_args, **_kwargs: [object()])
    monkeypatch.setattr(
        audit.socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()),
    )

    result = audit.audit_postgres()

    assert result["diagnostics"]["dns_ok"] is True
    assert result["diagnostics"]["tcp_5432_ok"] is False
    assert result["diagnostics"]["postgres_connect_ok"] is False
    assert result["issues"][0]["reason"] == "database_tcp_connection_failed"


def test_markdown_has_required_sections_and_no_blob_sample_path() -> None:
    blob = audit._blob_base()
    blob.update({
        "status": "ok", "container_count": 1, "blob_count": 1, "bytes": 42,
        "containers": [{
            "name": "raw", "status": "ok", "blob_count": 1, "bytes": 42,
            "latest_modified": None,
            "prefixes": [{"name": "krx/stock_price", "blob_count": 1, "bytes": 42}],
        }],
    })
    blob["diagnostics"] = {name: True for name in blob["diagnostics"]}
    postgres = audit._postgres_base()
    text = audit.render_markdown({
        "generated_at": "2026-08-25T00:00:00+00:00", "blob": blob, "postgres": postgres,
    })

    assert "## 1. Azure Blob Storage" in text
    assert "## 2. PostgreSQL" in text
    assert "## 3. 데이터 역할 정리" in text
    assert "## 4. 발견된 문제" in text
    assert "krx/stock_price" in text
    assert "Example path" not in text
