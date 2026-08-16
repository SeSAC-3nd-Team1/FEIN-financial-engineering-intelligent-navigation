from datetime import date

import pytest
import requests

from collectors.public_data_client import PublicDataApiError, PublicDataClient, decode_page
from collectors.public_data_config import OPERATIONS, select_operations
from scripts.collect_public_data import group_items_by_month, parse_item_date


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
