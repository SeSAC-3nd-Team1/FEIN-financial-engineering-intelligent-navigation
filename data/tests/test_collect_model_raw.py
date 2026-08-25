"""모델 Raw 수집기의 partition·manifest·정합성 계약을 검증한다."""

from __future__ import annotations

from datetime import date
import json

import pytest

from collectors.krx_config import OPERATIONS
from scripts.collect_model_raw import (
    CoverageManifest,
    ModelRawCollector,
    _month_starts,
    _range_partition,
    _validate_disclosures,
    _validate_krx,
    _weekdays,
)
from storage.blob import BlobObject


class FakeStorage:
    """coverage manifest 테스트에 필요한 Blob 동작만 메모리에서 제공한다."""

    upload_max_concurrency = 4

    def __init__(self, paths: list[str] | None = None) -> None:
        self.paths = list(paths or [])
        self.objects: dict[str, bytes] = {}

    def exists(self, _container: str, path: str) -> bool:
        return path in self.objects

    def list_paths(self, _container: str, *, prefix: str = "") -> list[str]:
        return sorted(path for path in self.paths if path.startswith(prefix))

    def has_paths(self, _container: str, *, prefix: str) -> bool:
        return any(path.startswith(prefix) for path in self.paths)

    def download_bytes(self, _container: str, path: str) -> bytes:
        return self.objects[path]

    def upload_bytes(
        self, container: str, path: str, data: bytes, *, metadata=None, **_kwargs
    ) -> BlobObject:
        self.objects[path] = data
        return BlobObject(container, path, len(data), "etag", dict(metadata or {}), True)


def test_month_chunks_and_weekdays_cover_requested_range() -> None:
    assert _month_starts(date(2026, 1, 31), date(2026, 3, 1)) == [
        date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)
    ]
    assert _weekdays(date(2026, 8, 21), date(2026, 8, 24)) == [
        date(2026, 8, 21), date(2026, 8, 24)
    ]
    assert _range_partition(
        date(2026, 8, 1), date(2026, 8, 24), date(2026, 8, 24)
    ) == "2026-08-24..2026-08-24"


def test_manifest_round_trip_marks_only_successful_partition() -> None:
    storage = FakeStorage()
    manifest = CoverageManifest(storage, "raw")
    manifest.mark(
        source="krx", dataset="stock_price", operation="stk_bydd_trd",
        partition="2026-08-24", rows=3, blob_count=1,
    )
    storage.paths.append(
        "krx/stock_price/operation=stk_bydd_trd/year=2026/month=08/a.jsonl.gz"
    )
    manifest.save()

    loaded = CoverageManifest(storage, "raw")
    assert loaded.is_completed("krx", "stock_price", "stk_bydd_trd", "2026-08-24")
    payload = json.loads(storage.objects["_manifests/model_raw_coverage.json"])
    entry = payload["entries"]["krx|stock_price|stk_bydd_trd"]
    assert entry["record_count"] == 3
    assert entry["completed_partitions"] == ["2026-08-24"]


def test_blob_bootstrap_skips_historical_month_but_not_current_month() -> None:
    prefix = "krx/stock_price/operation=stk_bydd_trd/"
    storage = FakeStorage([
        prefix + "year=2025/month=12/a.jsonl.gz",
        prefix + "year=2026/month=08/b.jsonl.gz",
    ])
    manifest = CoverageManifest(storage, "raw")

    months = manifest.bootstrap_historical_months(
        source="krx", dataset="stock_price", operation="stk_bydd_trd",
        prefix=prefix, current_month="2026-08",
    )

    assert months == {"2025-12"}
    assert manifest.is_completed("krx", "stock_price", "stk_bydd_trd", "2025-12-15")
    assert not manifest.is_completed("krx", "stock_price", "stk_bydd_trd", "2026-08-24")


def test_krx_validation_preserves_leading_zero_and_requires_ohlcv() -> None:
    operation = OPERATIONS[0]
    valid = {
        "BAS_DD": "20260824", "ISU_CD": "005930", "TDD_OPNPRC": "70000",
        "TDD_HGPRC": "71000", "TDD_LWPRC": "69000", "TDD_CLSPRC": "70500",
        "ACC_TRDVOL": "100", "ACC_TRDVAL": "7050000",
    }
    _validate_krx(operation, [valid], date(2026, 8, 24))

    with pytest.raises(RuntimeError, match="OHLCV"):
        _validate_krx(operation, [{**valid, "ACC_TRDVOL": ""}], date(2026, 8, 24))

    master = next(item for item in OPERATIONS if item.dataset == "stock_master")
    _validate_krx(
        master, [{"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자"}],
        date(2026, 8, 24),
    )


def test_opendart_disclosure_validation_requires_pit_identity() -> None:
    _validate_disclosures([
        {"rcept_no": "202608240001", "corp_code": "00126380", "rcept_dt": "20260824"}
    ])
    with pytest.raises(RuntimeError, match="rcept_dt"):
        _validate_disclosures([
            {"rcept_no": "202608240001", "corp_code": "00126380", "rcept_dt": ""}
        ])


def test_concurrency_is_bounded_even_when_environment_is_excessive(monkeypatch) -> None:
    monkeypatch.setenv("KRX_MAX_CONCURRENCY", "1000")
    monkeypatch.setenv("ECOS_MAX_CONCURRENCY", "1000")
    monkeypatch.setenv("OPENDART_MAX_CONCURRENCY", "1000")
    storage = FakeStorage()
    collector = ModelRawCollector(
        storage, container="raw", manifest=CoverageManifest(storage, "raw"),
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
    )

    assert collector.concurrency == {"krx": 16, "ecos-bok": 4, "opendart": 4}
