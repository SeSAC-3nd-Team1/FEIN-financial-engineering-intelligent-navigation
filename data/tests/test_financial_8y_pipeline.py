"""2018-01-01 통합 백필의 범위·배치·재실행 계약을 검증한다."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from collectors.opendart_client import OpenDartClient
from loaders.opendart import CASH_FLOW_COLUMNS, OpenDartRepository
from processing.coverage import coverage_is_complete, summarize_trading_dates
from scripts.backfill_opendart_8y import (
    DEFAULT_START_DATE as DART_START_DATE,
    _normalize_multi_financial_items,
    _quarter_windows,
)
from scripts.run_financial_8y_pipeline import (
    DEFAULT_START_DATE,
    OPENDART_LOOKBACK_DAYS,
    _incremental_start,
)
from scripts.sync_krx import _load_checkpoint, _save_checkpoint
from scripts.verify_krx_history_coverage import _expected_months


class _Response:
    status_code = 200

    def __init__(self, payload: dict, content: bytes = b"raw") -> None:
        self.payload = payload
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class _Session:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict] = []

    def get(self, _url, *, params, timeout):
        self.calls.append(dict(params))
        payload = self.payloads.pop(0)
        return _Response(payload)


def test_project_baseline_is_2018_january_first() -> None:
    assert DEFAULT_START_DATE == date(2018, 1, 1)
    assert DART_START_DATE == date(2018, 1, 1)


def test_opendart_multi_financials_batches_company_codes_in_one_parameter() -> None:
    session = _Session([{"status": "000", "list": []}])
    client = OpenDartClient("secret", session=session, min_interval_seconds=0)

    client.financials_multi(["00126380", "00334624"], "2018", "11011")

    assert session.calls[0]["corp_code"] == "00126380,00334624"
    assert session.calls[0]["bsns_year"] == "2018"
    assert session.calls[0]["reprt_code"] == "11011"


def test_opendart_multi_financials_rejects_more_than_100_companies() -> None:
    session = _Session([])
    client = OpenDartClient("secret", session=session, min_interval_seconds=0)
    corp_codes = [f"{value:08d}" for value in range(101)]

    with pytest.raises(ValueError, match="at most 100"):
        client.financials_multi(corp_codes, "2018", "11011")

    assert session.calls == []


def test_opendart_market_disclosures_follow_all_pages() -> None:
    session = _Session(
        [
            {"status": "000", "total_page": 2, "list": [{"rcept_no": "1"}]},
            {"status": "000", "total_page": 2, "list": [{"rcept_no": "2"}]},
        ]
    )
    client = OpenDartClient("secret", session=session, min_interval_seconds=0)

    pages = client.disclosures_market(
        start_date="20180101",
        end_date="20180331",
        corp_cls="Y",
    )

    assert len(pages) == 2
    assert [call["page_no"] for call in session.calls] == [1, 2]
    assert all(call["corp_cls"] == "Y" for call in session.calls)
    assert all(call["page_count"] == 100 for call in session.calls)


def test_quarter_windows_cover_range_without_gaps() -> None:
    windows = list(_quarter_windows(date(2018, 1, 1), date(2018, 8, 25)))

    assert windows == [
        (date(2018, 1, 1), date(2018, 3, 31)),
        (date(2018, 4, 1), date(2018, 6, 30)),
        (date(2018, 7, 1), date(2018, 8, 25)),
    ]


def test_multi_financial_rows_recover_corp_code_from_requested_stock_mapping() -> None:
    grouped = _normalize_multi_financial_items(
        [
            {
                "stock_code": "005930",
                "fs_div": "CFS",
                "account_nm": "매출액",
                "bsns_year": "2018",
                "reprt_code": "11011",
            }
        ],
        [("00126380", "005930")],
    )

    assert grouped[("005930", "CFS")][0]["corp_code"] == "00126380"


def test_incremental_start_uses_baseline_on_first_run_and_last_success_for_ecos() -> None:
    assert _incremental_start({}, "ecos", DEFAULT_START_DATE, refresh=False) == DEFAULT_START_DATE
    state = {"ecos": {"last_success_end": "2026-08-24"}}
    assert _incremental_start(state, "ecos", DEFAULT_START_DATE, refresh=False) == date(2026, 8, 24)
    assert _incremental_start(state, "ecos", DEFAULT_START_DATE, refresh=True) == DEFAULT_START_DATE


def test_opendart_incremental_start_rechecks_recent_quarter_for_late_filing() -> None:
    """4월 초 실행에서 비었던 1분기 보고서를 이후 실행이 다시 조회해야 한다."""

    state = {"opendart": {"last_success_end": "2026-04-05"}}
    start = _incremental_start(state, "opendart", DEFAULT_START_DATE, refresh=False)

    assert OPENDART_LOOKBACK_DAYS == 120
    assert start == date(2025, 12, 6)
    assert start <= date(2026, 3, 31)


def test_sparse_dart_summary_does_not_update_cash_flow_columns(monkeypatch) -> None:
    captured: dict = {}

    def fake_upsert(session, model, rows, *, conflict_columns, update_columns=None):
        captured["update_columns"] = update_columns
        return len(rows)

    monkeypatch.setattr("loaders.opendart.upsert_rows", fake_upsert)
    row = {
        "corp_code": "00126380",
        "stock_code": "005930",
        "business_year": "2025",
        "report_code": "11011",
        "quarter": "FY",
        "fs_div": "CFS",
        "revenue": 1,
        "operating_income": 1,
        "net_income": 1,
        "total_assets": 1,
        "total_liabilities": 1,
        "total_equity": 1,
        "operating_cash_flow": None,
        "investing_cash_flow": None,
        "financing_cash_flow": None,
    }

    assert OpenDartRepository(object()).upsert_financials([row]) == 1
    assert captured["update_columns"] is not None
    assert all(column not in captured["update_columns"] for column in CASH_FLOW_COLUMNS)


def test_full_dart_summary_can_still_update_cash_flow_columns(monkeypatch) -> None:
    captured: dict = {}

    def fake_upsert(session, model, rows, *, conflict_columns, update_columns=None):
        captured["update_columns"] = update_columns
        return len(rows)

    monkeypatch.setattr("loaders.opendart.upsert_rows", fake_upsert)
    row = {
        "corp_code": "00126380",
        "business_year": "2025",
        "report_code": "11011",
        "fs_div": "CFS",
        "operating_cash_flow": 10,
        "investing_cash_flow": -5,
        "financing_cash_flow": 2,
    }

    OpenDartRepository(object()).upsert_financials([row])
    assert captured["update_columns"] is None


def test_krx_coverage_rejects_missing_middle_year() -> None:
    start = date(2018, 1, 1)
    end = date(2026, 8, 25)
    dates = [
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
        if (start + timedelta(days=offset)).weekday() < 5
        and (start + timedelta(days=offset)).year != 2023
    ]
    coverage = summarize_trading_dates(dates, start_date=start, end_date=end)

    assert coverage.max_gap_days > 300
    assert not coverage_is_complete(coverage, start_date=start, end_date=end)


def test_krx_coverage_rejects_stock_series_starting_two_years_late() -> None:
    start = date(2018, 1, 1)
    end = date(2026, 8, 25)
    stock_start = date(2020, 1, 2)
    dates = [
        stock_start + timedelta(days=offset)
        for offset in range((end - stock_start).days + 1)
        if (stock_start + timedelta(days=offset)).weekday() < 5
    ]
    coverage = summarize_trading_dates(dates, start_date=start, end_date=end)

    assert not coverage_is_complete(coverage, start_date=start, end_date=end)


def test_krx_expected_months_exposes_missing_partition() -> None:
    expected = _expected_months(date(2022, 11, 1), date(2023, 2, 28))
    actual = {(2022, 11), (2022, 12), (2023, 2)}

    assert expected - actual == {(2023, 1)}


def test_krx_checkpoint_round_trip_is_sorted_and_resume_safe(tmp_path: Path) -> None:
    path = tmp_path / "krx.json"
    completed = {"2018-01-03", "2018-01-02"}

    _save_checkpoint(path, completed)

    assert _load_checkpoint(path) == completed
    content = path.read_text(encoding="utf-8")
    assert content.index("2018-01-02") < content.index("2018-01-03")
