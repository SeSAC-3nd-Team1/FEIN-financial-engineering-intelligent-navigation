"""KRX client와 canonical mapping의 외부 계약을 검증한다."""

from datetime import date
from decimal import Decimal

import pytest

from collectors.krx_client import KrxApiError, KrxClient
from collectors.krx_config import OPERATIONS
from processing.krx import market_index_rows, stock_master_rows, stock_price_rows


class FakeResponse:
    def __init__(self, payload: object, *, status_error: bool = False) -> None:
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self) -> None:
        if self.status_error:
            raise RuntimeError("HTTP details must not leak")

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    def mount(self, *_args) -> None:
        return None

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


def test_krx_client_uses_auth_header_and_base_date() -> None:
    operation = OPERATIONS[0]
    client = KrxClient("secret", base_url="https://example.invalid", timeout_seconds=3)
    fake = FakeSession(FakeResponse({"OutBlock_1": [{"BAS_DD": "20260821"}]}))
    client.session = fake

    assert client.fetch(operation, "20260821") == [{"BAS_DD": "20260821"}]
    assert fake.calls == [{
        "url": "https://example.invalid/sto/stk_bydd_trd",
        "headers": {"AUTH_KEY": "secret"},
        "params": {"basDd": "20260821"},
        "timeout": 3,
    }]


def test_krx_client_rejects_invalid_response_shape() -> None:
    client = KrxClient("secret")
    client.session = FakeSession(FakeResponse({"OutBlock_1": {}}))

    with pytest.raises(KrxApiError, match="response rows are invalid"):
        client.fetch(OPERATIONS[0], "20260821")


def test_stock_master_mapping_preserves_six_digit_code() -> None:
    rows = stock_master_rows([{
        "ISU_CD": "KR7005930003",
        "ISU_SRT_CD": "005930",
        "ISU_NM": "삼성전자보통주",
        "ISU_ABBRV": "삼성전자",
        "ISU_ENG_NM": "Samsung Electronics",
        "LIST_DD": "19750611",
        "MKT_TP_NM": "KOSPI",
        "SECUGRP_NM": "주권",
        "SECT_TP_NM": "전기전자",
        "LIST_SHRS": "5969782550",
    }], market="KOSPI", as_of=date(2026, 8, 21))

    assert rows[0]["stock_code"] == "005930"
    assert rows[0]["market"] == "KOSPI"
    assert rows[0]["listing_date"] == date(1975, 6, 11)


def test_stock_price_mapping_keeps_source_and_market_cap() -> None:
    rows = stock_price_rows([{
        "BAS_DD": "20260821",
        "ISU_CD": "005930",
        "MKT_NM": "KOSPI",
        "TDD_CLSPRC": "73800",
        "CMPPREVDD_PRC": "1200",
        "FLUC_RT": "1.66",
        "TDD_OPNPRC": "73000",
        "TDD_HGPRC": "74200",
        "TDD_LWPRC": "72800",
        "ACC_TRDVOL": "12345678",
        "ACC_TRDVAL": "900000000000",
        "MKTCAP": "438000000000000",
        "LIST_SHRS": "5969782550",
    }], market="KOSPI", as_of=date(2026, 8, 21))

    assert rows[0]["stock_code"] == "005930"
    assert rows[0]["market_cap"] == 438000000000000
    assert rows[0]["source"] == "KRX"


def test_mapping_rejects_stock_code_without_leading_zero() -> None:
    with pytest.raises(ValueError, match="stock code"):
        stock_price_rows([{
            "BAS_DD": "20260821", "ISU_CD": "5930", "MKT_NM": "KOSPI",
            "TDD_CLSPRC": "1", "TDD_OPNPRC": "1", "TDD_HGPRC": "1",
            "TDD_LWPRC": "1", "ACC_TRDVOL": "0",
        }], market="KOSPI", as_of=date(2026, 8, 21))


def test_market_index_mapping_allows_missing_optional_ohlc() -> None:
    rows = market_index_rows([{
        "BAS_DD": "20260821",
        "IDX_CLSS": "KOSPI",
        "IDX_NM": "코스피",
        "CLSPRC_IDX": "3000.12",
        "OPNPRC_IDX": "",
        "HGPRC_IDX": "",
        "LWPRC_IDX": "",
    }], market="KOSPI", as_of=date(2026, 8, 21))

    assert rows[0]["index_code"] == "KOSPI:KOSPI:코스피"
    assert rows[0]["open_value"] is None
    assert rows[0]["close_value"] == Decimal("3000.12")
