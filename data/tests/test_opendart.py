"""OpenDART parsing, 정규화, UPSERT 충돌키를 검증한다."""

from datetime import UTC, date, datetime
from decimal import Decimal
import io
import zipfile

import pytest

from collectors.opendart_client import (
    OpenDartApiError,
    OpenDartClient,
    OpenDartNotConfiguredError,
    parse_corp_code_zip,
)
from loaders.opendart import OpenDartRepository
from processing.opendart import (
    dividend_rows,
    disclosure_rows,
    financial_account_rows,
    financial_summary_row,
)
from storage.blob import BlobObject
from storage.opendart import OpenDartRawWriter


def _corp_zip() -> bytes:
    xml = b"""<?xml version='1.0' encoding='UTF-8'?>
    <result><list><corp_code>00126380</corp_code><corp_name>Samsung Electronics</corp_name>
    <corp_eng_name>Samsung Electronics Co., Ltd.</corp_eng_name><stock_code>005930</stock_code>
    <modify_date>20260824</modify_date></list></result>"""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("CORPCODE.xml", xml)
    return output.getvalue()


def test_corp_code_xml_parsing_preserves_stock_code_leading_zero() -> None:
    records = parse_corp_code_zip(_corp_zip())
    assert len(records) == 1
    assert records[0].corp_code == "00126380"
    assert records[0].stock_code == "005930"


def test_missing_api_key_fails_without_http_request() -> None:
    with pytest.raises(OpenDartNotConfiguredError):
        OpenDartClient("")


class _Response:
    status_code = 200

    def __init__(self, payload: dict, content: bytes = b"original-json-bytes") -> None:
        self.payload = payload
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class _Session:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.params = None
        self.calls = []

    def get(self, _url, *, params, timeout):
        self.params = params
        self.calls.append(params)
        return _Response(self.payload)


def test_client_includes_key_and_returns_validated_response() -> None:
    session = _Session(
        {"status": "000", "total_page": 1, "list": [{"corp_code": "00126380"}]}
    )
    client = OpenDartClient("secret", session=session, min_interval_seconds=0)
    responses = client.disclosures("00126380")
    assert responses[0].payload["list"][0]["corp_code"] == "00126380"
    assert responses[0].content == b"original-json-bytes"
    assert session.params["crtfc_key"] == "secret"


def test_client_uses_shared_rate_limiter_when_provided() -> None:
    """여러 worker가 각자 Session을 써도 요청 시작 간격은 공통 limiter를 거친다."""

    calls: list[str] = []
    client = OpenDartClient(
        "secret",
        session=_Session({"status": "000", "list": []}),
        min_interval_seconds=0,
        rate_limiter=lambda: calls.append("wait"),
    )

    client.company("00126380")

    assert calls == ["wait"]


def test_disclosures_follow_page_no_until_total_page() -> None:
    class SequenceSession:
        def __init__(self) -> None:
            self.page_numbers = []

        def get(self, _url, *, params, timeout):
            page_no = params["page_no"]
            self.page_numbers.append(page_no)
            return _Response(
                {
                    "status": "000",
                    "total_page": 3,
                    "list": [{"rcept_no": f"page-{page_no}"}],
                },
                content=f"raw-page-{page_no}".encode(),
            )

    session = SequenceSession()
    client = OpenDartClient("secret", session=session, min_interval_seconds=0)
    responses = client.disclosures("00126380", limit=100)
    assert session.page_numbers == [1, 2, 3]
    assert [response.content for response in responses] == [
        b"raw-page-1",
        b"raw-page-2",
        b"raw-page-3",
    ]
    assert [response.payload["list"][0]["rcept_no"] for response in responses] == [
        "page-1",
        "page-2",
        "page-3",
    ]


def test_disclosures_stop_after_requested_limit() -> None:
    class SequenceSession:
        def __init__(self) -> None:
            self.page_numbers = []

        def get(self, _url, *, params, timeout):
            page_no = params["page_no"]
            self.page_numbers.append(page_no)
            return _Response(
                {
                    "status": "000",
                    "total_page": 10,
                    "list": [
                        {"rcept_no": f"{page_no}-1"},
                        {"rcept_no": f"{page_no}-2"},
                    ],
                }
            )

    session = SequenceSession()
    client = OpenDartClient("secret", session=session, min_interval_seconds=0)
    responses = client.disclosures("00126380", limit=3)
    assert session.page_numbers == [1, 2]
    assert len(responses) == 2


@pytest.mark.parametrize("status", ["020", "901"])
def test_non_retryable_limit_and_account_status_fail_once(status: str) -> None:
    session = _Session({"status": status, "message": "not retryable"})
    client = OpenDartClient(
        "secret", session=session, min_interval_seconds=0, max_attempts=3
    )
    with pytest.raises(OpenDartApiError) as error:
        client.company("00126380")
    assert error.value.retryable is False
    assert len(session.calls) == 1


def test_client_raises_for_opendart_status_error() -> None:
    client = OpenDartClient(
        "secret",
        session=_Session({"status": "010", "message": "invalid key"}),
        min_interval_seconds=0,
    )
    with pytest.raises(OpenDartApiError) as error:
        client.company("00126380")
    assert error.value.status == "010"
    assert "secret" not in str(error.value)


def test_dividend_client_calls_alot_matter_with_annual_report() -> None:
    session = _Session({"status": "000", "list": []})

    OpenDartClient("secret", session=session, min_interval_seconds=0).dividends(
        "00126380", "2025"
    )

    assert session.params["corp_code"] == "00126380"
    assert session.params["bsns_year"] == "2025"
    assert session.params["reprt_code"] == "11011"


def test_dividend_rows_parse_common_and_preferred_without_double_counting() -> None:
    payload = {
        "list": [
            {
                "rcept_no": "202603010001",
                "se": "현금배당금총액(백만원)",
                "stock_knd": "-",
                "thstrm": "9,000",
                "stlm_dt": "2025-12-31",
            },
            {
                "rcept_no": "202603010001",
                "se": "(연결)현금배당성향(%)",
                "stock_knd": "-",
                "thstrm": "20.5",
                "stlm_dt": "2025-12-31",
            },
            {
                "rcept_no": "202603010001",
                "se": "현금배당수익률(%)",
                "stock_knd": "보통주",
                "thstrm": "2.0",
                "stlm_dt": "2025-12-31",
            },
            {
                "rcept_no": "202603010001",
                "se": "주당 현금배당금(원)",
                "stock_knd": "보통주",
                "thstrm": "1,500",
                "stlm_dt": "2025-12-31",
            },
            {
                "rcept_no": "202603010001",
                "se": "주당 현금배당금(원)",
                "stock_knd": "보통주",
                "thstrm": "1,500",
                "stlm_dt": "2025-12-31",
            },
            {
                "rcept_no": "202603010001",
                "se": "현금배당수익률(%)",
                "stock_knd": "우선주",
                "thstrm": "2.4",
                "stlm_dt": "2025-12-31",
            },
            {
                "rcept_no": "202603010001",
                "se": "주당 현금배당금(원)",
                "stock_knd": "우선주",
                "thstrm": "1,550",
                "stlm_dt": "2025-12-31",
            },
        ]
    }

    rows = dividend_rows(
        payload,
        stock_code="005930",
        corp_code="00126380",
        business_year="2025",
        report_code="11011",
        collected_at=datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert len(rows) == 2
    common = next(row for row in rows if row["stock_kind"] == "COMMON")
    preferred = next(row for row in rows if row["stock_kind"] == "PREFERRED")
    assert common["dividend_per_share"] == Decimal("1500")
    assert common["reported_dividend_yield"] == Decimal("2.0")
    assert common["total_dividend"] == Decimal("9000")
    assert common["dividend_payout_ratio"] == Decimal("20.5")
    assert common["settlement_date"] == date(2025, 12, 31)
    assert preferred["dividend_per_share"] == Decimal("1550")


def test_dividend_rows_do_not_fabricate_missing_values() -> None:
    rows = dividend_rows(
        {"list": [{"se": "주당 현금배당금(원)", "stock_knd": "보통주", "thstrm": "-"}]},
        stock_code="005930",
        corp_code="00126380",
        business_year="2025",
        report_code="11011",
    )

    assert rows == []


def test_financial_response_parsing_and_metric_aliases() -> None:
    payload = {
        "list": [
            {
                "corp_code": "00126380",
                "bsns_year": "2025",
                "reprt_code": "11011",
                "fs_div": "CFS",
                "sj_div": "IS",
                "account_id": "ifrs-full_Revenue",
                "account_nm": "매출액",
                "thstrm_amount": "300,000",
                "frmtrm_amount": "250,000",
                "currency": "KRW",
            },
            {
                "corp_code": "00126380",
                "bsns_year": "2025",
                "reprt_code": "11011",
                "fs_div": "CFS",
                "sj_div": "BS",
                "account_id": "ifrs-full_Assets",
                "account_nm": "자산총계",
                "thstrm_amount": "(10,000)",
                "frmtrm_amount": "9,000",
                "currency": "KRW",
            },
        ]
    }
    rows = financial_account_rows(payload, stock_code="005930")
    summary = financial_summary_row(rows)
    assert rows[0]["stock_code"] == "005930"
    assert rows[1]["current_amount"] == Decimal("-10000")
    assert summary["revenue"] == Decimal("300000")
    assert summary["total_assets"] == Decimal("-10000")
    assert summary["quarter"] == "FY"


def test_disclosure_rows_keep_unique_receipt_identity_fields() -> None:
    rows = disclosure_rows(
        {
            "list": [
                {
                    "rcept_no": "202608240001",
                    "corp_code": "00126380",
                    "corp_name": "삼성전자",
                    "stock_code": "005930",
                    "report_nm": "사업보고서",
                    "flr_nm": "삼성전자",
                    "rcept_dt": "20260824",
                    "rm": "유",
                }
            ]
        },
        stock_code="005930",
    )
    assert rows[0]["receipt_no"] == "202608240001"
    assert rows[0]["receipt_date"] == date(2026, 8, 24)


def test_repository_uses_domain_conflict_keys(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "loaders.opendart.upsert_rows",
        lambda session, model, rows, *, conflict_columns: calls.append(
            (model.__tablename__, tuple(conflict_columns))
        )
        or len(rows),
    )
    repository = OpenDartRepository(object())
    assert repository.upsert_companies([{"corp_code": "1"}]) == 1
    assert repository.upsert_financials([{"corp_code": "1"}]) == 1
    assert repository.upsert_dividends([{"stock_code": "005930"}]) == 1
    assert repository.upsert_disclosures([{"receipt_no": "1"}]) == 1
    assert calls == [
        ("companies", ("corp_code",)),
        ("company_financials", ("corp_code", "business_year", "report_code", "fs_div")),
        (
            "stock_dividends",
            ("stock_code", "business_year", "report_code", "stock_kind"),
        ),
        ("company_disclosures", ("receipt_no",)),
    ]


def test_opendart_raw_writer_keeps_original_bytes_and_daily_path() -> None:
    captured = {}

    class Storage:
        def upload_bytes(self, container, path, data, *, metadata, content_type):
            captured.update(
                container=container,
                path=path,
                data=data,
                metadata=metadata,
                content_type=content_type,
            )
            return BlobObject(container, path, len(data), "etag", metadata, True)

    content = b"unchanged-opendart-response"
    blob = OpenDartRawWriter(Storage(), container="raw").upload_bytes(
        dataset="financial",
        stock_code="005930",
        content=content,
        partition_date=date(2026, 8, 24),
        extension="json",
        content_type="application/json",
    )
    assert captured["data"] == content
    assert blob.path.startswith("opendart/financial/005930/2026/08/24/")
    assert blob.path.endswith(".json")
