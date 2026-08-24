"""ECOS client, 정규화, PIT feature 계산을 검증한다."""

from datetime import date

import pandas as pd
import pytest

from collectors.ecos_client import EcosApiError, EcosClient, EcosError, EcosNotConfiguredError
from collectors.ecos_config import ECOS_SERIES
from features.ecos import compute_macro_daily
from processing.ecos import normalize_ecos_records
from scripts.run_ecos_pipeline import _latest_raw_date
from storage.raw import serialize_jsonl_gzip


class _Response:
    """requests response의 ECOS client 사용 부분만 제공한다."""

    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_missing_key_fails_before_request() -> None:
    """빈 key는 HTTP 호출 전에 명확히 실패한다."""

    with pytest.raises(EcosNotConfiguredError):
        EcosClient("")


def test_client_paginates_and_does_not_leak_key() -> None:
    """전체 건수까지 page를 이동하며 key를 예외 문자열에 노출하지 않는다."""

    class Session:
        def __init__(self):
            self.urls = []

        def get(self, url, *, timeout):
            self.urls.append(url)
            row = [{"TIME": "20260101", "DATA_VALUE": "2.5"}]
            return _Response({"StatisticSearch": {"list_total_count": 2, "row": row}})

    session = Session()
    client = EcosClient("top-secret", session=session, page_size=1)
    rows = client.observations(ECOS_SERIES["base_rate"], date(2026, 1, 1), date(2026, 1, 2))
    assert len(rows) == 2
    assert "/1/1/" in session.urls[0] and "/2/2/" in session.urls[1]

    client = EcosClient("top-secret", session=type("S", (), {
        "get": lambda self, url, timeout: _Response({"RESULT": {"CODE": "ERR", "MESSAGE": "bad"}})
    })())
    with pytest.raises(EcosApiError) as error:
        client.observations(ECOS_SERIES["base_rate"], date(2026, 1, 1), date(2026, 1, 2))
    assert "top-secret" not in str(error.value)


def test_timeout_is_sanitized() -> None:
    """timeout 원인 URL에 key가 있어도 외부 예외에는 노출하지 않는다."""

    import requests

    class Session:
        def get(self, url, *, timeout):
            raise requests.Timeout(f"timeout at {url}")

    client = EcosClient("top-secret", session=Session(), max_attempts=1)
    with pytest.raises(EcosError) as error:
        client.observations(ECOS_SERIES["cpi"], date(2026, 1, 1), date(2026, 1, 31))
    assert "top-secret" not in str(error.value)
    assert error.value.__cause__ is None


def _record(time: str, value: str) -> dict:
    """정규화 테스트용 canonical Raw envelope을 만든다."""

    return {"payload": {"TIME": time, "DATA_VALUE": value}, "payloadHash": time}


def test_base_rate_raw_daily_rows_become_change_events() -> None:
    """provider 반복 행은 변경 이벤트로만 축약되고 품질 건수는 보존된다."""

    frame, quality = normalize_ecos_records([
        _record("20260101", "2.50"), _record("20260102", "2.50"),
        _record("20260103", "2.75"),
    ], ECOS_SERIES["base_rate"])
    assert frame["value"].tolist() == [2.5, 2.75]
    assert {
        "series", "observation_date", "available_at", "value", "unit", "source",
        "stat_code", "item_code", "frequency", "collected_at", "_payload_hash",
        "_source_blob",
    } == set(frame.columns)
    assert quality["source_rows"] == 3
    assert quality["accepted_rows"] == 2


def test_conflicting_natural_key_is_rejected() -> None:
    """동일 관측일에 서로 다른 값이 있으면 임의 선택하지 않는다."""

    with pytest.raises(RuntimeError, match="conflicting"):
        normalize_ecos_records([
            _record("20260102", "1400"), _record("20260102", "1401"),
        ], ECOS_SERIES["usd_krw"])


def test_null_bad_unit_and_raw_serialization_are_auditable() -> None:
    """결측·단위 변경은 reject되고 canonical Raw payload는 그대로 직렬화된다."""

    source = {"TIME": "20260102", "DATA_VALUE": "1400", "UNIT_NAME": "달러"}
    frame, quality = normalize_ecos_records([
        {"payload": source}, {"payload": {"TIME": "20260103", "DATA_VALUE": ""}},
    ], ECOS_SERIES["usd_krw"])
    assert frame.empty
    assert quality["rejection_reasons"] == {"unit_mismatch": 1, "invalid_observation": 1}
    batch = serialize_jsonl_gzip([{"payloadHash": "hash", "payload": source}])
    import gzip
    import json
    assert json.loads(gzip.decompress(batch.data))["payload"] == source


def _frame(dates, values, available=None):
    """PIT 테스트용 Processed frame을 만든다."""

    observed = pd.to_datetime(dates)
    return pd.DataFrame({
        "observation_date": observed,
        "available_at": pd.to_datetime(available) if available is not None else observed,
        "value": values,
    })


def test_macro_daily_uses_available_at_and_trading_dates() -> None:
    """CPI는 가용일 전 노출되지 않고 주말 행도 생성하지 않는다."""

    trading = ["2026-02-27", "2026-03-02", "2026-03-03"]
    frames = {
        "base_rate": _frame(["2026-01-01"], [2.5]),
        "usd_krw": _frame(trading, [1400, 1410, 1420]),
        "cpi": _frame(["2026-01-01"], [110.0], ["2026-03-01"]),
        "treasury_3y": _frame(trading, [3.0, 3.1, 3.2]),
        "treasury_10y": _frame(trading, [3.5, 3.7, 3.8]),
    }
    result = compute_macro_daily(frames)
    assert result["date"].dt.strftime("%Y-%m-%d").tolist() == trading
    assert pd.isna(result.loc[0, "cpi"])
    assert result.loc[1, "cpi"] == 110.0
    assert result.loc[1, "usd_krw_return_1d"] == pytest.approx(1410 / 1400 - 1)
    assert result.loc[2, "yield_spread_10y_3y"] == pytest.approx(0.6)


def test_cpi_yoy_is_computed_on_monthly_observations() -> None:
    """CPI YoY는 일별 forward-fill 후가 아니라 12개월 전 원 관측값과 계산한다."""

    months = pd.date_range("2025-01-01", periods=13, freq="MS")
    trading = ["2026-03-02"]
    frames = {
        "base_rate": _frame(["2025-01-01"], [2.5]),
        "usd_krw": _frame(trading, [1400]),
        "cpi": _frame(months, list(range(100, 113)), months + pd.offsets.MonthBegin(2)),
        "treasury_3y": _frame(trading, [3.0]),
        "treasury_10y": _frame(trading, [3.5]),
    }
    result = compute_macro_daily(frames)
    assert result.loc[0, "cpi_yoy"] == pytest.approx(0.12)


def test_incremental_checkpoint_comes_from_latest_raw_payload() -> None:
    """증분 수집 기준일은 mutable 상태가 아니라 canonical Raw의 마지막 TIME에서 복원한다."""

    import gzip
    import json

    class Storage:
        def list_paths(self, container, *, prefix):
            return [prefix + "year=2026/month=01/a.jsonl.gz"]

        def download_bytes(self, container, path):
            rows = [{"payload": {"TIME": "20260102"}}, {"payload": {"TIME": "20260105"}}]
            return gzip.compress(b"\n".join(json.dumps(row).encode() for row in rows))

    assert _latest_raw_date(Storage(), "raw", "usd_krw", "D") == date(2026, 1, 5)


@pytest.mark.skipif(not __import__("os").getenv("ECOS_API_KEY"), reason="ECOS_API_KEY not configured")
def test_ecos_live_smoke() -> None:
    """실제 key가 있을 때 registry의 모든 공식 ECOS 조합을 smoke 검증한다."""

    import os

    client = EcosClient(os.environ["ECOS_API_KEY"])
    for series in ECOS_SERIES.values():
        rows = client.observations(series, date(2026, 1, 1), date(2026, 2, 28))
        assert rows, series.name
