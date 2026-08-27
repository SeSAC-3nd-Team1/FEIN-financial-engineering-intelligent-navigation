"""KRX client와 canonical mapping의 외부 계약을 검증한다."""

from argparse import Namespace
from datetime import date, timedelta
from decimal import Decimal

import pytest
import requests

from collectors.krx_client import KrxApiError, KrxClient
from collectors.krx_config import OPERATIONS
from processing.krx import market_index_rows, stock_master_rows, stock_price_rows
from scripts.sync_krx import _parser, _sync_dates
from scripts.verify_krx_backfill import Coverage, _is_complete


class FakeResponse:
    def __init__(
        self,
        payload: object,
        *,
        status_error: bool = False,
        status_code: int = 200,
    ) -> None:
        self.payload = payload
        self.status_error = status_error
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_error:
            raise requests.HTTPError(response=self)

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


def test_krx_client_reports_status_without_leaking_auth_or_body() -> None:
    client = KrxClient("secret-value")
    client.session = FakeSession(FakeResponse(
        {"message": "sensitive-provider-body"},
        status_error=True,
        status_code=403,
    ))

    with pytest.raises(KrxApiError) as raised:
        client.fetch(OPERATIONS[0], "20260821")

    message = str(raised.value)
    assert "status=403" in message
    assert "secret-value" not in message
    assert "sensitive-provider-body" not in message


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


def test_stock_rows_skip_six_character_alphanumeric_instruments() -> None:
    master = stock_master_rows([{
        "ISU_SRT_CD": "00104K", "ISU_NM": "지원 밖 종목", "MKT_TP_NM": "KOSPI",
    }], market="KOSPI", as_of=date(2026, 8, 21))
    prices = stock_price_rows([{
        "BAS_DD": "20260821", "ISU_CD": "00104K", "MKT_NM": "KOSPI",
        "TDD_CLSPRC": "1", "TDD_OPNPRC": "1", "TDD_HGPRC": "1",
        "TDD_LWPRC": "1", "ACC_TRDVOL": "0",
    }], market="KOSPI", as_of=date(2026, 8, 21))

    assert master == []
    assert prices == []


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


def test_market_index_mapping_skips_row_without_close_value() -> None:
    rows = market_index_rows([{
        "BAS_DD": "20260821",
        "IDX_CLSS": "KOSPI",
        "IDX_NM": "코스피 (외국주포함)",
        "CLSPRC_IDX": "",
    }], market="KOSPI", as_of=date(2026, 8, 21))

    assert rows == []


def test_sync_dates_returns_inclusive_weekday_backfill_range() -> None:
    args = Namespace(date=None, start_date="2026-08-21", end_date="2026-08-25")

    assert list(_sync_dates(args, _parser())) == [
        date(2026, 8, 21),
        date(2026, 8, 24),
        date(2026, 8, 25),
    ]


def test_backfill_coverage_allows_weekend_boundaries() -> None:
    trade_dates = tuple(
        date(2021, 8, 24) + timedelta(days=offset)
        for offset in range((date(2026, 8, 24) - date(2021, 8, 24)).days + 1)
        if (date(2021, 8, 24) + timedelta(days=offset)).weekday() < 5
    )
    coverage = Coverage(
        trade_dates=trade_dates,
        rows=3_000_000,
    )

    assert _is_complete(coverage, date(2021, 8, 21), date(2026, 8, 25))


def test_backfill_coverage_rejects_partial_range() -> None:
    coverage = Coverage(
        trade_dates=(date(2025, 5, 26), date(2025, 8, 25)),
        rows=172_219,
    )

    assert not _is_complete(coverage, date(2020, 8, 25), date(2025, 8, 25))


def test_backfill_coverage_rejects_missing_middle_year() -> None:
    start_date = date(2021, 8, 25)
    end_date = date(2026, 8, 25)
    trade_dates = tuple(
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
        if (start_date + timedelta(days=offset)).weekday() < 5
        and (start_date + timedelta(days=offset)).year != 2023
    )
    coverage = Coverage(trade_dates=trade_dates, rows=2_000_000)

    assert not _is_complete(coverage, start_date, end_date)


def test_sync_dates_requires_complete_ordered_range() -> None:
    with pytest.raises(SystemExit):
        list(_sync_dates(Namespace(date=None, start_date="2026-08-25", end_date=None), _parser()))
    with pytest.raises(SystemExit):
        list(_sync_dates(
            Namespace(date=None, start_date="2026-08-25", end_date="2026-08-24"),
            _parser(),
        ))


def test_sync_dates_keeps_explicit_weekend_date_for_manual_diagnostics() -> None:
    args = Namespace(date="2026-08-23", start_date=None, end_date=None)

    assert list(_sync_dates(args, _parser())) == [date(2026, 8, 23)]
