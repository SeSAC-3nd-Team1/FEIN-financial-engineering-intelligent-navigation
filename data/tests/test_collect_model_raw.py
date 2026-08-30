"""모델 Raw 수집기의 partition·manifest·정합성 계약을 검증한다."""

from __future__ import annotations

from datetime import date, timedelta
import gzip
import hashlib
import json

import pytest

import scripts.collect_model_raw as collect_module
from collectors.krx_config import OPERATIONS
from collectors.opendart_client import OpenDartJsonResponse
from scripts.audit_model_raw import audit
from scripts.collect_model_raw import (
    CoverageManifest,
    ModelRawCollector,
    _month_starts,
    _financial_checkpoint_allowed,
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


def test_blob_audit_counts_unique_financial_rows_and_complete_disclosure_pages() -> None:
    storage = FakeStorage()
    payloads = {
        "opendart/financial_multi/2026/06/30/a.json": {
            "status": "000",
            "list": [{
                "corp_code": "00126380", "stock_code": "0008Z0",
                "bsns_year": "2026", "reprt_code": "11012",
                "fs_div": "CFS", "sj_div": "BS", "account_id": "ifrs_Assets",
            }],
        },
        "opendart/disclosure_market/2026/08/01/y.json": {
            "status": "000", "page_no": 1, "total_page": 1,
            "list": [{
                "corp_code": "00126380", "corp_cls": "Y",
                "rcept_no": "202608010001", "rcept_dt": "20260801",
            }],
        },
        "opendart/disclosure_market/2026/08/01/k.json": {
            "status": "000", "page_no": 1, "total_page": 1,
            "list": [{
                "corp_code": "00164779", "corp_cls": "K",
                "rcept_no": "202608010002", "rcept_dt": "20260801",
            }],
        },
    }
    storage.paths.extend(payloads)
    storage.objects.update({
        path: json.dumps(payload).encode() for path, payload in payloads.items()
    })

    result = audit(
        start=date(2026, 8, 1), end=date(2026, 8, 31), workers=2,
        storage=storage, container="raw",
    )

    assert result["complete"] is True
    assert result["financial"]["rows"] == 1
    assert result["financial"]["unique_logical_rows"] == 1
    assert result["disclosure"]["present_month_market_groups"] == 2
    assert result["disclosure"]["missing_groups"] == []


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
    assert payload["schema_version"] == 2
    assert entry["record_count"] == 3
    assert entry["completed_partitions"] == ["2026-08-24"]


def test_blob_bootstrap_skips_historical_month_but_not_current_month() -> None:
    prefix = "ecos-bok/ecos/operation=usd_krw/"
    storage = FakeStorage([
        prefix + "year=2025/month=12/a.jsonl.gz",
        prefix + "year=2026/month=08/b.jsonl.gz",
    ])
    manifest = CoverageManifest(storage, "raw")

    months = manifest.bootstrap_historical_months(
        source="ecos-bok", dataset="ecos", operation="usd_krw",
        prefix=prefix, current_month="2026-08",
    )

    assert months == {"2025-12"}
    assert manifest.is_completed("ecos-bok", "ecos", "usd_krw", "2025-12-15")
    assert not manifest.is_completed("ecos-bok", "ecos", "usd_krw", "2026-08-24")


def test_krx_bootstrap_keeps_dates_missing_when_month_is_only_partially_loaded() -> None:
    """월 prefix가 있어도 실제 anchor에 없는 거래일을 전체 완료로 승격하지 않는다."""

    storage = FakeStorage()
    for operation in OPERATIONS:
        path = (
            f"krx/{operation.dataset}/operation={operation.name}/"
            "year=2025/month=12/a.jsonl.gz"
        )
        storage.paths.append(path)
        payload = {
            "payload": (
                {"BAS_DD": "20251201"}
                if operation.name == "kospi_dd_trd"
                else {}
            )
        }
        storage.objects[path] = gzip.compress(json.dumps(payload).encode())
    manifest = CoverageManifest(storage, "raw")
    collector = ModelRawCollector(
        storage, container="raw", manifest=manifest,
        start_date=date(2025, 12, 1), end_date=date(2025, 12, 2),
    )

    collector._bootstrap_krx_dates()

    assert all(
        manifest.is_completed("krx", operation.dataset, operation.name, "2025-12-01")
        for operation in OPERATIONS
    )
    assert all(
        not manifest.is_completed("krx", operation.dataset, operation.name, "2025-12-02")
        for operation in OPERATIONS
    )


def test_recent_krx_completion_without_anchor_is_refetched(monkeypatch) -> None:
    """최근 날짜는 manifest만 완료여도 실제 KOSPI Raw가 없으면 다시 확인한다."""

    target = date(2026, 8, 25)
    storage = FakeStorage()
    manifest = CoverageManifest(storage, "raw")
    for operation in OPERATIONS:
        manifest.mark(
            source="krx", dataset=operation.dataset, operation=operation.name,
            partition=target.isoformat(), rows=0, blob_count=0,
        )
    collector = ModelRawCollector(
        storage, container="raw", manifest=manifest,
        start_date=target, end_date=target,
    )
    monkeypatch.setattr(collect_module, "_seoul_today", lambda: date(2026, 8, 26))
    monkeypatch.setattr(collector, "_bootstrap_krx_dates", lambda: None)
    monkeypatch.setattr(collector, "_krx_anchor_dates", lambda _month: set())
    fetched: list[date] = []

    def fetch(value: date) -> dict[str, tuple[int, int]]:
        fetched.append(value)
        return {operation.name: (0, 0) for operation in OPERATIONS}

    monkeypatch.setattr(collector, "_krx_date", fetch)

    collector.collect_krx()

    assert fetched == [target]


def test_krx_anchor_requires_all_dated_operations() -> None:
    """최근 거래일은 가격·지수 5종이 실제 Blob에 모두 있어야 완성으로 본다."""

    target = date(2026, 8, 25)
    storage = FakeStorage()
    dated_operations = [
        operation for operation in OPERATIONS if operation.dataset != "stock_master"
    ]
    for operation in dated_operations[:-1]:
        path = (
            f"krx/{operation.dataset}/operation={operation.name}/"
            "year=2026/month=08/a.jsonl.gz"
        )
        storage.paths.append(path)
        storage.objects[path] = gzip.compress(json.dumps({
            "payload": {"BAS_DD": "20260825"}
        }).encode())
    collector = ModelRawCollector(
        storage, container="raw", manifest=CoverageManifest(storage, "raw"),
        start_date=target, end_date=target,
    )

    assert collector._krx_anchor_dates(date(2026, 8, 1)) == set()


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


def test_recent_opendart_013_is_retried_until_rows_are_available() -> None:
    """최근 013은 미완료이고 이후 000 응답은 완료 checkpoint를 허용한다."""

    period_end = date(2026, 6, 30)
    today = date(2026, 8, 25)

    assert not _financial_checkpoint_allowed("013", period_end, today=today)
    assert _financial_checkpoint_allowed("000", period_end, today=today)
    assert _financial_checkpoint_allowed("013", date(2025, 12, 31), today=today)


def test_dart_financial_013_then_000_rows_changes_checkpoint_result(monkeypatch) -> None:
    """실제 수집 함수도 013은 보류하고 이후 행이 생긴 000만 완료로 반환한다."""

    class Client:
        def __init__(self) -> None:
            self.responses = [
                OpenDartJsonResponse(b'{"status":"013"}', {"status": "013"}),
                OpenDartJsonResponse(
                    b'{"status":"000","list":[{}]}',
                    {
                        "status": "000",
                        "list": [{
                            "corp_code": "00126380", "stock_code": "0008Z0",
                            "bsns_year": "2026", "reprt_code": "11012",
                        }],
                    },
                ),
            ]

        def financials_multi(self, _codes, _year, _report_code):
            return self.responses.pop(0)

    storage = FakeStorage()
    collector = ModelRawCollector(
        storage, container="raw", manifest=CoverageManifest(storage, "raw"),
        start_date=date(2026, 6, 1), end_date=date(2026, 8, 25),
    )
    client = Client()
    monkeypatch.setattr(collector, "_dart_client", lambda: client)

    assert collector._dart_financial(["00126380"], 2026, "11012") == (0, 0, False)
    assert collector._dart_financial(["00126380"], 2026, "11012") == (1, 1, True)


def test_dart_financial_quarantines_mixed_year_and_retries_clean_codes(
    monkeypatch,
) -> None:
    """다른 사업연도 행은 원문 격리하고 정상 기업만 다시 요청해 canonical을 보존한다."""

    good_code = "00126380"
    bad_code = "00442455"

    class Client:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def financials_multi(self, codes, year, report_code):
            self.calls.append(list(codes))
            if len(self.calls) == 1:
                rows = [
                    {
                        "corp_code": good_code, "stock_code": "005930",
                        "bsns_year": year, "reprt_code": report_code,
                    },
                    {
                        "corp_code": bad_code, "stock_code": "082660",
                        "bsns_year": "2025", "reprt_code": report_code,
                    },
                ]
            else:
                rows = [{
                    "corp_code": good_code, "stock_code": "005930",
                    "bsns_year": year, "reprt_code": report_code,
                }]
            payload = {"status": "000", "list": rows}
            return OpenDartJsonResponse(json.dumps(payload).encode(), payload)

    storage = FakeStorage()
    manifest = CoverageManifest(storage, "raw")
    collector = ModelRawCollector(
        storage, container="raw", manifest=manifest,
        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
    )
    client = Client()
    monkeypatch.setattr(collector, "_dart_client", lambda: client)

    assert collector._dart_financial(
        [good_code, bad_code], 2024, "11011"
    ) == (1, 1, True)
    assert client.calls == [[good_code, bad_code], [good_code]]
    assert any("financial_multi_anomaly" in path for path in storage.objects)
    assert any(
        "opendart/financial_multi/2024/12/31" in path for path in storage.objects
    )
    digest = hashlib.sha256(
        f"{good_code},{bad_code}".encode()
    ).hexdigest()[:16]
    partition = f"2024-11011-{digest}"
    entry = manifest.data["entries"]["opendart|financial_multi|financial_multi"]
    assert entry["anomalies"][partition]["corp_codes"] == [bad_code]
    assert entry["anomalies"][partition]["observed_years"] == ["2025"]


def test_dart_disclosure_uploads_each_page_before_requesting_next(monkeypatch) -> None:
    """대량 공시는 전체 list를 쌓지 않고 page별 업로드 후 다음 page를 요청한다."""

    storage = FakeStorage()
    observed_object_counts: list[int] = []

    class Client:
        def iter_disclosures_market(self, **kwargs):
            assert kwargs["start_page"] == 1
            for page_no in range(1, 4):
                observed_object_counts.append(len(storage.objects))
                row = {
                    "rcept_no": f"202608{page_no:02d}0001",
                    "corp_code": "00126380",
                    "rcept_dt": f"202608{page_no:02d}",
                }
                yield OpenDartJsonResponse(
                    json.dumps({
                        "status": "000", "total_page": 3, "list": [row],
                    }).encode(),
                    {"status": "000", "total_page": 3, "list": [row]},
                )

    manifest = CoverageManifest(storage, "raw")
    collector = ModelRawCollector(
        storage, container="raw", manifest=manifest,
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
    )
    monkeypatch.setattr(collector, "_dart_client", lambda: Client())

    assert collector._dart_disclosure(date(2026, 8, 1), "Y") == (3, 3, True)
    assert observed_object_counts == [0, 1, 2]
    partition = "2026-08-01..2026-08-31-Y"
    assert manifest.partial_page(
        "opendart", "disclosure_market", "disclosure_market", partition
    ) == 3
    assert manifest.partial_progress(
        "opendart", "disclosure_market", "disclosure_market", partition
    ) == (3, 3, 3)

    manifest.mark(
        source="opendart", dataset="disclosure_market",
        operation="disclosure_market", partition=partition, rows=3, blob_count=3,
    )
    assert manifest.partial_page(
        "opendart", "disclosure_market", "disclosure_market", partition
    ) == 0


def test_dart_disclosure_resumes_with_checkpoint_totals(monkeypatch) -> None:
    """재시작은 완료 page를 건너뛰고 이전 누적 집계를 partition 결과에 포함한다."""

    storage = FakeStorage()
    manifest = CoverageManifest(storage, "raw")
    partition = "2026-08-01..2026-08-31-Y"
    manifest.mark_partial_page(
        source="opendart", dataset="disclosure_market",
        operation="disclosure_market", partition=partition,
        page_no=2, rows=200, blob_count=2,
    )

    class Client:
        def iter_disclosures_market(self, **kwargs):
            assert kwargs["start_page"] == 3
            row = {
                "rcept_no": "202608030001",
                "corp_code": "00126380",
                "rcept_dt": "20260803",
            }
            yield OpenDartJsonResponse(
                json.dumps({"status": "000", "total_page": 3, "list": [row]}).encode(),
                {"status": "000", "total_page": 3, "list": [row]},
            )

    collector = ModelRawCollector(
        storage, container="raw", manifest=manifest,
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
    )
    monkeypatch.setattr(collector, "_dart_client", lambda: Client())

    assert collector._dart_disclosure(date(2026, 8, 1), "Y") == (201, 3, True)
    assert manifest.partial_progress(
        "opendart", "disclosure_market", "disclosure_market", partition
    ) == (3, 201, 3)


def test_dart_disclosure_completed_partial_does_not_request_page_past_total(
    monkeypatch,
) -> None:
    """마지막 page checkpoint는 total_page + 1 호출 없이 완료로 승격한다."""

    storage = FakeStorage()
    manifest = CoverageManifest(storage, "raw")
    partition = "2026-08-01..2026-08-31-K"
    manifest.mark_partial_page(
        source="opendart", dataset="disclosure_market",
        operation="disclosure_market", partition=partition,
        page_no=68, rows=6746, blob_count=68, total_page=68,
    )

    class Client:
        def iter_disclosures_market(self, **_kwargs):
            raise AssertionError("completed partial must not call OpenDART")

    collector = ModelRawCollector(
        storage, container="raw", manifest=manifest,
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
    )
    monkeypatch.setattr(collector, "_dart_client", lambda: Client())

    assert collector._dart_disclosure(date(2026, 8, 1), "K") == (6746, 68, True)


def test_manifest_drops_partial_page_when_dataset_blobs_are_missing() -> None:
    """부분 checkpoint만 남고 실제 dataset Blob이 없으면 앞 page를 건너뛰지 않는다."""

    storage = FakeStorage()
    manifest = CoverageManifest(storage, "raw")
    partition = "2026-08-01..2026-08-31-Y"
    manifest.mark_partial_page(
        source="opendart", dataset="disclosure_market",
        operation="disclosure_market", partition=partition,
        page_no=5, rows=500, blob_count=5,
    )
    manifest.save()

    loaded = CoverageManifest(storage, "raw")

    assert loaded.partial_progress(
        "opendart", "disclosure_market", "disclosure_market", partition
    ) == (0, 0, 0)


def test_v1_manifest_drops_only_recent_legacy_financial_checkpoint() -> None:
    """v1의 최근 013 오완료 가능성은 제거하고 충분히 오래된 partition은 유지한다."""

    today = date.today()
    report_periods = [
        (date(year, month, day), code)
        for year in (today.year - 1, today.year)
        for code, (month, day) in {
            "11013": (3, 31), "11012": (6, 30),
            "11014": (9, 30), "11011": (12, 31),
        }.items()
        if date(year, month, day) <= today
    ]
    recent_end, recent_code = max(report_periods)
    assert today - recent_end <= timedelta(days=120)
    recent = f"{recent_end.year}-{recent_code}-recent"
    old = f"{today.year - 2}-11011-old"
    storage = FakeStorage(["opendart/financial_multi/old.json"])
    storage.objects["_manifests/model_raw_coverage.json"] = json.dumps({
        "schema_version": 1,
        "entries": {
            "opendart|financial_multi|financial_multi": {
                "source": "opendart", "dataset": "financial_multi",
                "operation": "financial_multi", "completed_partitions": [recent, old],
            }
        },
    }).encode()

    manifest = CoverageManifest(storage, "raw")
    completed = manifest.completed("opendart", "financial_multi", "financial_multi")

    assert recent not in completed
    assert old in completed
    assert manifest.data["schema_version"] == 2


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


def test_financial_batches_keep_existing_order_when_corp_snapshot_reorders() -> None:
    """회사목록 순서가 바뀌어도 완료 batch digest는 유지하고 신규 회사만 분리한다."""

    storage = FakeStorage()
    manifest = CoverageManifest(storage, "raw")
    first = [f"{value:08d}" for value in range(1, 101)]
    second = [f"{value:08d}" for value in range(101, 111)]
    manifest.data["opendart_financial_batches"] = [first.copy(), second.copy()]
    manifest.data["opendart_financial_base_batch_count"] = 2
    collector = ModelRawCollector(
        storage, container="raw", manifest=manifest,
        start_date=date(2026, 1, 1), end_date=date(2026, 8, 31),
    )

    batches = collector._stable_financial_chunks(
        list(reversed(first + second)) + ["00000111", "00000112"]
    )

    assert batches[:2] == [first, second]
    assert batches[2] == ["00000111", "00000112"]


def test_opendart_failure_keeps_other_partition_checkpoint(monkeypatch) -> None:
    """한 future가 실패해도 나머지 성공 partition을 완료 처리한 뒤 실패를 보고한다."""

    monkeypatch.setenv("OPENDART_MAX_CONCURRENCY", "1")
    storage = FakeStorage()
    manifest = CoverageManifest(storage, "raw")
    collector = ModelRawCollector(
        storage, container="raw", manifest=manifest,
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
    )
    monkeypatch.setattr(collector, "_corp_codes", lambda: ["00126380"])

    def disclosure(_month, corp_cls):
        if corp_cls == "Y":
            raise RuntimeError("provider anomaly")
        return 10, 1, 1

    monkeypatch.setattr(collector, "_dart_disclosure", disclosure)

    with pytest.raises(RuntimeError, match="partitions=1"):
        collector.collect_opendart()

    assert not manifest.is_completed(
        "opendart", "disclosure_market", "disclosure_market",
        "2026-08-01..2026-08-31-Y",
    )
    assert manifest.is_completed(
        "opendart", "disclosure_market", "disclosure_market",
        "2026-08-01..2026-08-31-K",
    )
