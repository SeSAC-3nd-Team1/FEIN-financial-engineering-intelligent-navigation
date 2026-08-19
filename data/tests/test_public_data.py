from argparse import Namespace
from datetime import date

import pytest
import requests

from collectors.public_data_client import PublicDataApiError, PublicDataClient, decode_page
from collectors.public_data_config import OPERATIONS, select_operations
from scripts.backfill_public_data_by_date import iter_dates, resolve_operation
from scripts.audit_raw_coverage import (
    assert_required_coverage,
    summarize_raw_coverage,
)
from scripts.collect_public_data import (
    filter_items_by_date_range,
    group_items_by_month,
    parse_item_date,
    resolve_date_range,
    subtract_calendar_years,
)


def test_official_operation_catalog_contains_all_datasets() -> None:
    assert len(OPERATIONS) == 8
    assert len(OPERATIONS["disclosure"]) == 33
    assert len(select_operations(list(OPERATIONS), include_all=True)) == 52


def test_decode_standard_nested_response() -> None:
    page = decode_page(
        {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
                "body": {
                    "pageNo": 1,
                    "totalCount": 2,
                    "items": {"item": [{"srtnCd": "005930"}]},
                },
            }
        },
        requested_page=1,
    )
    assert page.total_count == 2
    assert page.items == [{"srtnCd": "005930"}]


def test_decode_rejects_api_error_without_leaking_key() -> None:
    with pytest.raises(PublicDataApiError, match="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"):
        decode_page(
            {"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}},
            requested_page=1,
        )


def test_request_failure_does_not_leak_service_key(monkeypatch) -> None:
    client = PublicDataClient(api_key="super-secret-key")

    def fail_request(*args, **kwargs):
        raise requests.Timeout("https://apis.data.go.kr/example?serviceKey=super-secret-key")

    monkeypatch.setattr(client.session, "get", fail_request)
    with pytest.raises(PublicDataApiError) as captured:
        client.fetch_page(OPERATIONS["stock_price"][0], page_number=1, rows_per_page=1)
    assert "super-secret-key" not in str(captured.value)
    assert "Timeout" in str(captured.value)


def test_parse_item_date() -> None:
    assert parse_item_date("20260813") == date(2026, 8, 13)
    assert parse_item_date("not-a-date") is None
    assert parse_item_date(None) is None


def test_group_items_by_month_splits_at_basdt_month_boundary() -> None:
    items = [
        {"basDt": "20251231", "srtnCd": "005930"},
        {"basDt": "20260102", "srtnCd": "005930"},
    ]
    original = [dict(item) for item in items]
    grouped = group_items_by_month(items)
    assert [month for month, _ in grouped] == [date(2025, 12, 1), date(2026, 1, 1)]
    assert items == original


def test_group_items_by_month_uses_only_basdt() -> None:
    item = {"basDt": "20260813", "dvdnBasDt": "20191231", "cashDvdnPayDt": "20200401"}
    assert group_items_by_month([item]) == [(date(2026, 8, 1), [item])]


def test_group_items_by_month_requires_valid_basdt() -> None:
    with pytest.raises(ValueError, match="requires a valid basDt"):
        group_items_by_month([{"dvdnBasDt": "20231231"}])


def test_filter_items_by_exact_date_rejects_server_overfetch() -> None:
    items = [
        {"basDt": "20260817", "srtnCd": "005930"},
        {"basDt": "20260818", "srtnCd": "005930"},
        {"basDt": "invalid", "srtnCd": "005930"},
    ]
    assert filter_items_by_date_range(
        items,
        start_date=date(2026, 8, 18),
        end_date=date(2026, 8, 18),
    ) == [{"basDt": "20260818", "srtnCd": "005930"}]


def test_subtract_calendar_years_handles_leap_day() -> None:
    assert subtract_calendar_years(date(2024, 2, 29), 5) == date(2019, 2, 28)


def test_resolve_five_year_history_range() -> None:
    args = Namespace(
        date=None,
        start_date=None,
        end_date=date(2026, 8, 19),
        history_years=5,
    )
    assert resolve_date_range(args) == (date(2021, 8, 19), date(2026, 8, 19))


def test_raw_coverage_requires_five_full_calendar_years() -> None:
    paths = [
        "data-go-kr/stock_price/operation=getstockpriceinfo/"
        f"year={year}/month={month:02d}/{'a' * 64}.jsonl.gz"
        for year, month in ((2021, 8), (2026, 8))
    ]
    summaries = summarize_raw_coverage(paths, minimum_years=5)
    assert summaries[0]["month_span"] == 60
    assert summaries[0]["meets_minimum_years"] is True
    assert summaries[0]["missing_months"] == 59
    assert_required_coverage(summaries, ["stock_price/getstockpriceinfo"])


def test_raw_coverage_rejects_short_required_operation() -> None:
    paths = [
        "data-go-kr/market_index/operation=getstockmarketindex/"
        f"year=2022/month=08/{'b' * 64}.jsonl.gz",
        "data-go-kr/market_index/operation=getstockmarketindex/"
        f"year=2026/month=08/{'c' * 64}.jsonl.gz",
    ]
    summaries = summarize_raw_coverage(paths, minimum_years=5)
    with pytest.raises(RuntimeError, match="minimum Raw coverage not met"):
        assert_required_coverage(summaries, ["market_index/getstockmarketindex"])


def test_iter_dates_is_inclusive() -> None:
    assert iter_dates(date(2026, 8, 18), date(2026, 8, 20)) == [
        date(2026, 8, 18),
        date(2026, 8, 19),
        date(2026, 8, 20),
    ]


def test_resolve_operation_is_case_insensitive() -> None:
    operation = resolve_operation("stock_issuance", "getstocissustat_v3")
    assert operation.name == "getStocIssuStat_V3"
