"""2018 OpenDART Processed의 정규화·resume·PIT 안전 계약을 검증한다."""

from __future__ import annotations

from datetime import date
import io
import json
import zipfile

import pandas as pd
import pytest

from processing.model_opendart import (
    audit_opendart_processed,
    build_opendart_processed,
)
from storage.blob import BlobObject


class FakeStorage:
    """OpenDART Processed 테스트에 필요한 Blob 동작을 메모리에서 제공한다."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.upload_counts: dict[tuple[str, str], int] = {}

    def exists(self, container: str, path: str) -> bool:
        return (container, path) in self.objects

    def list_paths(self, container: str, *, prefix: str = "") -> list[str]:
        return sorted(
            path
            for stored_container, path in self.objects
            if stored_container == container and path.startswith(prefix)
        )

    def download_bytes(self, container: str, path: str) -> bytes:
        return self.objects[(container, path)]

    def upload_bytes(
        self, container: str, path: str, data: bytes, *, metadata=None, **_kwargs
    ) -> BlobObject:
        key = (container, path)
        self.objects[key] = data
        self.upload_counts[key] = self.upload_counts.get(key, 0) + 1
        return BlobObject(container, path, len(data), "etag", dict(metadata or {}), True)


def _corp_code_zip() -> bytes:
    """선행 0 종목코드가 있는 최소 corpCode ZIP fixture를 만든다."""

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<result><list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name>
<corp_eng_name>Samsung Electronics</corp_eng_name><stock_code>005930</stock_code>
<modify_date>20180101</modify_date></list></result>""".encode("utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("CORPCODE.xml", xml)
    return output.getvalue()


def _raw_storage() -> FakeStorage:
    """재무·공시 각 1행을 포함한 2018년 1월 Raw fixture를 만든다."""

    storage = FakeStorage()
    storage.objects[("raw", "opendart/corp_code/2018/01/corp.zip")] = _corp_code_zip()
    financial = {
        "status": "000",
        "list": [{
            "corp_code": "00126380",
            "bsns_year": "2018",
            "reprt_code": "11011",
            "fs_div": "CFS",
            "fs_nm": "연결재무제표",
            "sj_div": "BS",
            "sj_nm": "재무상태표",
            "account_id": "ifrs-full_Assets",
            "account_nm": "자산총계",
            "thstrm_nm": "제50기",
            "thstrm_end_dt": "2018.12.31",
            "thstrm_amount": "1,234,567",
            "frmtrm_amount": "(10)",
            "currency": "KRW",
            "ord": "1",
        }],
    }
    disclosure = {
        "status": "000",
        "list": [{
            "corp_code": "00126380",
            "corp_name": "삼성전자",
            "corp_cls": "Y",
            "report_nm": "사업보고서",
            "rcept_no": "201801020001",
            "rcept_dt": "20180102",
            "flr_nm": "삼성전자",
            "rm": "",
        }],
    }
    storage.objects[(
        "raw",
        "opendart/financial_multi/2018/01/31/" + "a" * 64 + ".json",
    )] = json.dumps(financial, ensure_ascii=False).encode()
    storage.objects[(
        "raw",
        "opendart/disclosure_market/2018/01/31/" + "b" * 64 + ".json",
    )] = json.dumps(disclosure, ensure_ascii=False).encode()
    return storage


def test_build_opendart_processed_preserves_exact_values_and_pit_safety() -> None:
    storage = _raw_storage()

    result = build_opendart_processed(
        storage,
        raw_container="raw",
        processed_container="processed",
        start_date=date(2018, 1, 1),
        end_date=date(2018, 1, 31),
    )

    financial_path = (
        "opendart_financial_accounts/operation=financial_multi/schema=v2/"
        "year=2018/month=01/part-00000.parquet"
    )
    disclosure_path = (
        "opendart_disclosures/operation=disclosure_market/schema=v2/"
        "year=2018/month=01/part-00000.parquet"
    )
    financial = pd.read_parquet(io.BytesIO(storage.objects[("processed", financial_path)]))
    disclosure = pd.read_parquet(io.BytesIO(storage.objects[("processed", disclosure_path)]))

    assert result["financial"]["status"] == "normalized_not_pit_ready"
    assert financial.loc[0, "stock_code"] == "005930"
    assert financial.loc[0, "current_amount"] == "1234567"
    assert financial.loc[0, "previous_amount"] == "-10"
    assert bool(financial.loc[0, "point_in_time_join_ready"]) is False
    assert pd.isna(financial.loc[0, "available_at"])
    assert disclosure.loc[0, "stock_code"] == "005930"
    assert disclosure.loc[0, "available_at"] == pd.Timestamp("2018-01-02")
    assert bool(disclosure.loc[0, "point_in_time_join_ready"]) is True


def test_build_opendart_processed_skips_unchanged_month() -> None:
    storage = _raw_storage()
    kwargs = {
        "raw_container": "raw",
        "processed_container": "processed",
        "start_date": date(2018, 1, 1),
        "end_date": date(2018, 1, 31),
    }

    build_opendart_processed(storage, **kwargs)
    parquet_key = (
        "processed",
        "opendart_financial_accounts/operation=financial_multi/schema=v2/"
        "year=2018/month=01/part-00000.parquet",
    )
    first_count = storage.upload_counts[parquet_key]
    build_opendart_processed(storage, **kwargs)

    assert storage.upload_counts[parquet_key] == first_count


def test_opendart_audit_requires_every_disclosure_month() -> None:
    storage = _raw_storage()
    build_opendart_processed(
        storage,
        raw_container="raw",
        processed_container="processed",
        start_date=date(2018, 1, 1),
        end_date=date(2018, 1, 31),
    )

    with pytest.raises(RuntimeError, match="missing_disclosure_months"):
        audit_opendart_processed(
            storage,
            processed_container="processed",
            schema_version="2",
            start_date=date(2018, 1, 1),
            end_date=date(2018, 2, 28),
        )


def test_opendart_audit_accepts_complete_month_and_keeps_financial_blocked() -> None:
    storage = _raw_storage()
    build_opendart_processed(
        storage,
        raw_container="raw",
        processed_container="processed",
        start_date=date(2018, 1, 1),
        end_date=date(2018, 1, 31),
    )

    result = audit_opendart_processed(
        storage,
        processed_container="processed",
        schema_version="2",
        start_date=date(2018, 1, 1),
        end_date=date(2018, 1, 31),
    )

    assert result["status"] == "ok"
    assert result["financial_point_in_time_join_ready"] is False
