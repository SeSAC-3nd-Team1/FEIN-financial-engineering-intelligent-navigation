from datetime import date

import pytest
import requests

from collectors.public_data_client import (
    PublicDataApiError,
    PublicDataClient,
    decode_page,
)
from collectors.public_data_config import OPERATIONS, select_operations
from loaders.public_data import (
    landing_rows,
    normalize_market_indices,
    normalize_stock_prices,
)
from loaders.stocks import normalize_stock_code


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
            {
                "response": {
                    "header": {
                        "resultCode": "30",
                        "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
                    }
                }
            },
            requested_page=1,
        )


def test_request_failure_does_not_leak_service_key(monkeypatch) -> None:
    client = PublicDataClient(api_key="super-secret-key")

    def fail_request(*args, **kwargs):
        raise requests.Timeout(
            "https://apis.data.go.kr/example?serviceKey=super-secret-key"
        )

    monkeypatch.setattr(client.session, "get", fail_request)
    with pytest.raises(PublicDataApiError) as captured:
        client.fetch_page(
            OPERATIONS["stock_price"][0],
            page_number=1,
            rows_per_page=1,
        )
    assert "super-secret-key" not in str(captured.value)
    assert "Timeout" in str(captured.value)


def test_landing_rows_extract_identifiers_and_hash() -> None:
    operation = OPERATIONS["stock_master"][0]
    item = {
        "basDt": "20260813",
        "srtnCd": "005930",
        "isinCd": "KR7005930003",
        "crno": "1301110006246",
        "corpNm": "삼성전자주식회사",
    }
    first = landing_rows(operation, [item])[0]
    second = landing_rows(operation, [dict(reversed(list(item.items())))])[0]
    assert first["reference_date"] == date(2026, 8, 13)
    assert first["payload_hash"] == second["payload_hash"]
    assert first["stock_code"] == "005930"


def test_stock_code_normalizer_removes_public_data_prefix() -> None:
    assert normalize_stock_code("A005930") == "005930"
    assert normalize_stock_code("A900110") == "900110"
    assert normalize_stock_code("A0001A0") == "0001A0"
    assert normalize_stock_code("5930") == "005930"


def test_stock_price_normalizer_preserves_code_and_numeric_types() -> None:
    frame = normalize_stock_prices(
        [
            {
                "basDt": "20260813",
                "srtnCd": "A005930",
                "mkp": "80,000",
                "hipr": "81,000",
                "lopr": "79,500",
                "clpr": "80,700",
                "trqu": "12345678",
                "trPrc": "995000000000",
            }
        ]
    )
    row = frame.iloc[0]
    assert row["stock_code"] == "005930"
    assert row["trade_date"] == date(2026, 8, 13)
    assert str(row["close_price"]) == "80700"
    assert row["volume"] == 12_345_678


def test_market_index_code_includes_series_to_avoid_name_collisions() -> None:
    frame = normalize_market_indices(
        [
            {
                "basDt": "20260813",
                "idxCsf": "KOSPI시리즈",
                "idxNm": "IT 서비스",
                "clpr": "1284.83",
            },
            {
                "basDt": "20260813",
                "idxCsf": "KOSDAQ시리즈",
                "idxNm": "IT 서비스",
                "clpr": "669.09",
            },
        ]
    )
    assert frame["index_code"].is_unique
