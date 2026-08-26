"""서비스용 연간 배당 수집의 COMMON 기준 fallback을 검증한다."""

from contextlib import contextmanager
from types import SimpleNamespace

from scripts import sync_opendart_dividends as sync


@contextmanager
def _session_scope():
    yield object()


def _payload(stock_kind: str, dividend_yield: str) -> dict:
    return {
        "list": [
            {
                "rcept_no": "202603010001",
                "se": "현금배당수익률(%)",
                "stock_knd": stock_kind,
                "thstrm": dividend_yield,
                "stlm_dt": "2025-12-31",
            }
        ]
    }


def test_existing_keys_only_treat_common_stock_as_complete(monkeypatch) -> None:
    class Session:
        def execute(self, query):
            self.query = query
            return []

    session = Session()

    @contextmanager
    def session_scope():
        yield session

    monkeypatch.setattr(sync, "session_scope", session_scope)

    assert sync._existing_keys(range(2024, 2026), ["005930"]) == set()
    sql = str(session.query)
    assert "stock_dividends.stock_kind =" in sql


def test_preferred_only_latest_year_stores_then_falls_back_to_common(
    monkeypatch,
) -> None:
    responses = {
        "2025": _payload("우선주", "1.9"),
        "2024": _payload("보통주", "1.5"),
    }

    class Client:
        def __init__(self, *_args, **_kwargs):
            self.calls = []

        def dividends(self, _corp_code, year, _report_code):
            self.calls.append(year)
            return SimpleNamespace(payload=responses[year], content=year.encode())

    class RawWriter:
        uploaded_years = []

        @classmethod
        def from_env(cls):
            return cls()

        def upload_bytes(self, **kwargs):
            self.uploaded_years.append(kwargs["partition_date"].year)

    stored_rows = []

    class Repository:
        def __init__(self, _session):
            pass

        def upsert_dividends(self, rows):
            stored_rows.extend(rows)
            return len(rows)

    client = Client()
    monkeypatch.setattr(sync, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sync, "_targets", lambda _codes: [("00126380", "005930")])
    monkeypatch.setattr(sync, "_existing_keys", lambda _years, _codes: set())
    monkeypatch.setattr(sync, "OpenDartClient", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(sync, "OpenDartRawWriter", RawWriter)
    monkeypatch.setattr(sync, "OpenDartRepository", Repository)
    monkeypatch.setattr(sync, "session_scope", _session_scope)

    assert sync.main(["--year", "2025", "--fallback-year", "2024"]) == 0

    assert client.calls == ["2025", "2024"]
    assert [row["business_year"] for row in stored_rows] == ["2025", "2024"]
    assert [row["stock_kind"] for row in stored_rows] == ["PREFERRED", "COMMON"]
