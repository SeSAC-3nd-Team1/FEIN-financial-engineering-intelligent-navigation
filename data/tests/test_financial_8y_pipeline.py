"""2018-01-01 통합 백필의 범위·배치·재실행 계약을 검증한다."""

from __future__ import annotations

from argparse import Namespace
from datetime import date
from pathlib import Path

import pytest

from collectors.opendart_client import OpenDartClient
from scripts.backfill_opendart_8y import (
    DEFAULT_START_DATE as DART_START_DATE,
    _normalize_multi_financial_items,
    _quarter_windows,
)
from scripts.run_financial_8y_pipeline import (
    DEFAULT_START_DATE,
    _incremental_start,
)
from scripts.sync_krx import _load_checkpoint, _save_checkpoint


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


def test_incremental_start_uses_baseline_on_first_run_and_last_success_afterward() -> None:
    assert _incremental_start({}, "ecos", DEFAULT_START_DATE, refresh=False) == DEFAULT_START_DATE
    state = {"ecos": {"last_success_end": "2026-08-24"}}
    assert _incremental_start(state, "ecos", DEFAULT_START_DATE, refresh=False) == date(2026, 8, 24)
    assert _incremental_start(state, "ecos", DEFAULT_START_DATE, refresh=True) == DEFAULT_START_DATE


def test_krx_checkpoint_round_trip_is_sorted_and_resume_safe(tmp_path: Path) -> None:
    path = tmp_path / "krx.json"
    completed = {"2018-01-03", "2018-01-02"}

    _save_checkpoint(path, completed)

    assert _load_checkpoint(path) == completed
    content = path.read_text(encoding="utf-8")
    assert content.index("2018-01-02") < content.index("2018-01-03")
