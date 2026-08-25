"""KRX·ECOS·OpenDART 모델 Raw를 누락 partition만 병렬 수집한다."""

from __future__ import annotations

import argparse
import calendar
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Iterable

from dotenv import load_dotenv

from collectors.ecos_client import EcosClient
from collectors.ecos_config import ECOS_SERIES
from collectors.krx_client import KrxClient
from collectors.krx_config import OPERATIONS, KrxOperation
from collectors.opendart_client import OpenDartClient, parse_corp_code_zip
from storage import BlobStorage, RawBlobWriter
from storage.opendart import OpenDartRawWriter


DATA_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = DATA_ROOT.parent
DEFAULT_START_DATE = date(2018, 1, 1)
MANIFEST_PATH = "_manifests/model_raw_coverage.json"
MANIFEST_SCHEMA_VERSION = 2
SUMMARY_JSON_PATH = DATA_ROOT / "reports" / "MODEL_RAW_COLLECTION_SUMMARY.json"
SUMMARY_MARKDOWN_PATH = DATA_ROOT / "reports" / "MODEL_RAW_COLLECTION_SUMMARY.md"
INVENTORY_PATH = DATA_ROOT / "docs" / "DOYOUNG_MODEL_DATA_INVENTORY.md"
MONTH_PATTERN = re.compile(r"/year=(\d{4})/month=(\d{2})/")
REPORT_CODES = ("11013", "11012", "11014", "11011")
REPORT_PERIOD_END = {
    "11013": (3, 31),
    "11012": (6, 30),
    "11014": (9, 30),
    "11011": (12, 31),
}
OPENDART_FINANCIAL_LOOKBACK_DAYS = 120


def _bounded_env(name: str, default: int, maximum: int) -> int:
    """환경변수의 worker 수를 안전 범위로 제한한다."""

    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be at least 1")
    return min(value, maximum)


def _month_starts(start_date: date, end_date: date) -> list[date]:
    """닫힌 기간과 겹치는 월의 첫날을 순서대로 반환한다."""

    cursor = start_date.replace(day=1)
    result: list[date] = []
    while cursor <= end_date:
        result.append(cursor)
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return result


def _month_range(month: date, start_date: date, end_date: date) -> tuple[date, date]:
    next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return max(month, start_date), min(next_month - timedelta(days=1), end_date)


def _range_partition(month: date, start_date: date, end_date: date) -> str:
    """부분 월 실행을 월 전체 완료로 오인하지 않는 checkpoint key를 만든다."""

    start, end = _month_range(month, start_date, end_date)
    return f"{start.isoformat()}..{end.isoformat()}"


def _weekdays(start_date: date, end_date: date) -> list[date]:
    """KRX 휴장일 누락을 만들지 않도록 평일만 사전 제외한다."""

    return [
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
        if (start_date + timedelta(days=offset)).weekday() < 5
    ]


@dataclass
class SourceMetrics:
    """source별 호출·행·전송량과 구간 시간을 thread-safe하게 누적한다."""

    source: str
    api_calls: int = 0
    rows: int = 0
    uploaded_bytes: int = 0
    new_blobs: int = 0
    reused_blobs: int = 0
    skipped_partitions: int = 0
    completed_partitions: int = 0
    download_seconds: float = 0.0
    upload_seconds: float = 0.0
    started_at: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, **values: int | float) -> None:
        with self._lock:
            for name, value in values.items():
                setattr(self, name, getattr(self, name) + value)

    def reset_clock(self) -> None:
        """source가 실제로 시작할 때 ETA와 wall time 기준점을 맞춘다."""

        self.started_at = time.monotonic()

    def as_dict(self) -> dict[str, Any]:
        wall_elapsed = max(time.monotonic() - self.started_at, 0.000001)
        active_seconds = self.download_seconds + self.upload_seconds
        return {
            "source": self.source,
            "api_calls": self.api_calls,
            "rows": self.rows,
            "new_blobs": self.new_blobs,
            "reused_blobs": self.reused_blobs,
            "skipped_partitions": self.skipped_partitions,
            "completed_partitions": self.completed_partitions,
            "download_seconds": round(self.download_seconds, 3),
            "upload_seconds": round(self.upload_seconds, 3),
            "elapsed_seconds": round(wall_elapsed, 3),
            "active_seconds": round(active_seconds, 3),
            "rows_per_second": round(
                self.rows / max(self.download_seconds, 0.000001), 3
            ),
            "upload_mb_per_second": round(
                self.uploaded_bytes / 1_048_576 / max(self.upload_seconds, 0.000001), 3
            ),
            "uploaded_bytes": self.uploaded_bytes,
        }


class CoverageManifest:
    """Blob partition과 교차검증 가능한 경량 resume manifest를 관리한다."""

    def __init__(self, storage: BlobStorage, container: str) -> None:
        self.storage = storage
        self.container = container
        self._lock = threading.Lock()
        if storage.exists(container, MANIFEST_PATH):
            value = json.loads(storage.download_bytes(container, MANIFEST_PATH))
            if not isinstance(value, dict) or value.get("schema_version") not in {1, 2}:
                raise RuntimeError("invalid model Raw coverage manifest")
            self.data = value
        else:
            self.data = {"schema_version": MANIFEST_SCHEMA_VERSION, "entries": {}}
        previous_schema = int(self.data.get("schema_version", 1))
        # 과거 버전이 부분 실행을 YYYY-MM 전체 완료로 기록했을 수 있다. 진행 중인 달의
        # coarse key만 제거하고 날짜 범위 key는 유지해 최신일까지 다시 확인한다.
        active_month = date.today().strftime("%Y-%m")
        for entry in self.data.get("entries", {}).values():
            completed = entry.get("completed_partitions", [])
            entry["completed_partitions"] = [
                value for value in completed if value != active_month
            ]
            if entry.get("source") == "krx":
                entry["completed_partitions"] = [
                    value
                    for value in entry["completed_partitions"]
                    if not re.fullmatch(r"\d{4}-\d{2}", str(value))
                ]
        if previous_schema == 1:
            self._remove_recent_legacy_financial_checkpoints()
            self.data["schema_version"] = MANIFEST_SCHEMA_VERSION
        self._cross_validate_entries()

    def _remove_recent_legacy_financial_checkpoints(self) -> None:
        """v1이 013을 완료로 기록했을 수 있는 최근 재무 partition을 재검증 대상으로 돌린다."""

        cutoff = date.today() - timedelta(days=OPENDART_FINANCIAL_LOOKBACK_DAYS)
        for entry in self.data.get("entries", {}).values():
            if entry.get("source") != "opendart" or entry.get("dataset") != "financial_multi":
                continue
            retained: list[str] = []
            for partition in entry.get("completed_partitions", []):
                parts = str(partition).split("-", 2)
                try:
                    year = int(parts[0])
                    report_code = parts[1]
                    month, day = REPORT_PERIOD_END[report_code]
                    period_end = date(year, month, day)
                except (IndexError, KeyError, ValueError):
                    retained.append(partition)
                    continue
                if period_end < cutoff:
                    retained.append(partition)
            entry["completed_partitions"] = retained

    def _cross_validate_entries(self) -> None:
        """manifest가 가리키는 dataset prefix 자체가 사라졌으면 완료 상태를 폐기한다."""

        for entry in self.data.get("entries", {}).values():
            source = str(entry.get("source", ""))
            dataset = str(entry.get("dataset", ""))
            operation = str(entry.get("operation", ""))
            if source == "krx":
                prefix = f"krx/{dataset}/operation={operation}/"
            elif source == "ecos-bok":
                prefix = f"ecos-bok/{dataset}/operation={operation}/"
            elif source == "opendart":
                prefix = f"opendart/{dataset}/"
            else:
                continue
            has_paths = getattr(self.storage, "has_paths", None)
            exists = has_paths(self.container, prefix=prefix) if has_paths else bool(
                self.storage.list_paths(self.container, prefix=prefix)
            )
            if entry.get("completed_partitions") and not exists:
                entry["completed_partitions"] = []
            if entry.get("partial_pages") and not exists:
                entry["partial_pages"] = {}

    @staticmethod
    def key(source: str, dataset: str, operation: str) -> str:
        return f"{source}|{dataset}|{operation}"

    def completed(self, source: str, dataset: str, operation: str) -> set[str]:
        entry = self.data.get("entries", {}).get(self.key(source, dataset, operation), {})
        return set(entry.get("completed_partitions", []))

    def is_completed(
        self, source: str, dataset: str, operation: str, partition: str
    ) -> bool:
        completed = self.completed(source, dataset, operation)
        return partition in completed or partition[:7] in completed

    def mark(
        self,
        *,
        source: str,
        dataset: str,
        operation: str,
        partition: str,
        rows: int,
        blob_count: int,
    ) -> None:
        """검증과 업로드가 모두 끝난 partition만 완료 상태로 추가한다."""

        with self._lock:
            entries = self.data.setdefault("entries", {})
            key = self.key(source, dataset, operation)
            entry = entries.setdefault(
                key,
                {
                    "source": source,
                    "dataset": dataset,
                    "operation": operation,
                    "completed_partitions": [],
                    "record_count": 0,
                    "blob_count": 0,
                },
            )
            completed = set(entry.get("completed_partitions", []))
            if partition not in completed:
                completed.add(partition)
                entry["record_count"] = int(entry.get("record_count", 0)) + rows
                entry["blob_count"] = int(entry.get("blob_count", 0)) + blob_count
            entry["completed_partitions"] = sorted(completed)
            partial_pages = entry.get("partial_pages", {})
            if isinstance(partial_pages, dict):
                partial_pages.pop(partition, None)
                entry["partial_pages"] = partial_pages
            entry["min_date"] = min(completed) if completed else None
            entry["max_date"] = max(completed) if completed else None
            entry["last_success_at"] = datetime.now(timezone.utc).isoformat()

    def partial_page(
        self, source: str, dataset: str, operation: str, partition: str
    ) -> int:
        """중단된 pagination partition에서 마지막으로 원격 저장된 page를 반환한다."""

        return self.partial_progress(source, dataset, operation, partition)[0]

    def partial_progress(
        self, source: str, dataset: str, operation: str, partition: str
    ) -> tuple[int, int, int]:
        """마지막 저장 page와 해당 시점의 누적 row·Blob 수를 반환한다."""

        entry = self.data.get("entries", {}).get(self.key(source, dataset, operation), {})
        partial_pages = entry.get("partial_pages", {})
        if not isinstance(partial_pages, dict):
            return 0, 0, 0
        progress = partial_pages.get(partition, 0)
        if isinstance(progress, dict):
            try:
                return (
                    max(0, int(progress.get("page_no", 0))),
                    max(0, int(progress.get("record_count", 0))),
                    max(0, int(progress.get("blob_count", 0))),
                )
            except (TypeError, ValueError):
                return 0, 0, 0
        try:
            # 최초 streaming 구현의 page 번호 정수 형식도 안전하게 읽는다.
            return max(0, int(progress)), 0, 0
        except (TypeError, ValueError):
            return 0, 0, 0

    def mark_partial_page(
        self,
        *,
        source: str,
        dataset: str,
        operation: str,
        partition: str,
        page_no: int,
        rows: int,
        blob_count: int,
    ) -> None:
        """Blob 업로드가 끝난 page와 누적 집계를 resume checkpoint로 기록한다."""

        with self._lock:
            entries = self.data.setdefault("entries", {})
            key = self.key(source, dataset, operation)
            entry = entries.setdefault(
                key,
                {
                    "source": source,
                    "dataset": dataset,
                    "operation": operation,
                    "completed_partitions": [],
                    "record_count": 0,
                    "blob_count": 0,
                },
            )
            partial_pages = entry.setdefault("partial_pages", {})
            current_page = self.partial_progress(
                source, dataset, operation, partition
            )[0]
            if page_no >= current_page:
                partial_pages[partition] = {
                    "page_no": page_no,
                    "record_count": rows,
                    "blob_count": blob_count,
                }

    def save(self) -> None:
        """작은 manifest 하나만 overwrite해 중단 후 재개 지점을 원격에 보존한다."""

        with self._lock:
            self.data["updated_at"] = datetime.now(timezone.utc).isoformat()
            payload = json.dumps(self.data, ensure_ascii=False, indent=2).encode()
            # 여러 OpenDART worker가 checkpoint를 저장해도 오래된 payload가 나중에
            # overwrite하지 않도록 원격 업로드까지 같은 lock에서 직렬화한다.
            self.storage.upload_bytes(
                self.container,
                MANIFEST_PATH,
                payload,
                content_type="application/json",
                overwrite=True,
                metadata={
                    "dataset": "model_raw_coverage",
                    "schema_version": str(MANIFEST_SCHEMA_VERSION),
                },
            )

    def bootstrap_historical_months(
        self,
        *,
        source: str,
        dataset: str,
        operation: str,
        prefix: str,
        current_month: str,
    ) -> set[str]:
        """기존 Raw 경로에서 과거 월 coverage를 복원하되 현재 월은 완료로 추정하지 않는다."""

        months = {
            f"{match.group(1)}-{match.group(2)}"
            for path in self.storage.list_paths(self.container, prefix=prefix)
            if (match := MONTH_PATTERN.search(path)) and path.endswith(".jsonl.gz")
        }
        historical = months - {current_month}
        for month in historical:
            self.mark(
                source=source,
                dataset=dataset,
                operation=operation,
                partition=month,
                rows=0,
                blob_count=0,
            )
        return historical


def _raw_krx_date(content: bytes) -> date | None:
    """날짜가 있는 KRX anchor Raw 한 객체에서 거래일을 복원한다."""

    for raw_line in gzip.decompress(content).splitlines():
        payload = json.loads(raw_line).get("payload", {})
        value = str(payload.get("BAS_DD", ""))
        if len(value) == 8 and value.isdigit():
            return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    return None


def _financial_checkpoint_allowed(
    status: str, period_end: date, *, today: date | None = None
) -> bool:
    """최근 보고기간의 013은 늦은 공시가 도착할 수 있으므로 완료로 확정하지 않는다."""

    reference = today or date.today()
    return status != "013" or period_end < (
        reference - timedelta(days=OPENDART_FINANCIAL_LOOKBACK_DAYS)
    )


def _validate_krx(operation: KrxOperation, rows: list[dict[str, Any]], expected: date) -> None:
    """KRX 날짜·종목코드·OHLCV 핵심 필드를 Raw 업로드 전에 검증한다."""

    expected_text = expected.strftime("%Y%m%d")
    for row in rows:
        # 종목 Master API에는 BAS_DD가 없고 요청일 시점의 snapshot을 반환한다.
        # 가격·지수만 provider 거래일이 요청일과 정확히 일치해야 한다.
        if operation.dataset != "stock_master" and str(row.get("BAS_DD", "")) != expected_text:
            raise RuntimeError(f"KRX BAS_DD mismatch operation={operation.name}")
        if operation.dataset in {"stock_price", "stock_master"}:
            code_field = "ISU_SRT_CD" if operation.dataset == "stock_master" else "ISU_CD"
            code = str(row.get(code_field) or "").strip()
            if len(code) != 6 or not code.isalnum():
                raise RuntimeError(f"KRX stock code invalid operation={operation.name}")
        if operation.dataset == "stock_master" and not str(
            row.get("ISU_ABBRV") or row.get("ISU_NM") or ""
        ).strip():
            raise RuntimeError(f"KRX stock name missing operation={operation.name}")
        if operation.dataset == "stock_price":
            required = (
                "TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "TDD_CLSPRC",
                "ACC_TRDVOL", "ACC_TRDVAL",
            )
            if any(str(row.get(name, "")).strip() == "" for name in required):
                raise RuntimeError(f"KRX OHLCV missing operation={operation.name}")


def _validate_ecos(rows: list[dict[str, Any]], *, cycle: str, operation: str) -> None:
    """ECOS 관측시점·값·단위 계약을 최소 필수키 기준으로 검증한다."""

    time_length = 6 if cycle == "M" else 8
    for row in rows:
        value = str(row.get("TIME", ""))
        if len(value) != time_length or not value.isdigit():
            raise RuntimeError(f"ECOS TIME invalid operation={operation}")
        if str(row.get("DATA_VALUE", "")).strip() == "":
            raise RuntimeError(f"ECOS DATA_VALUE missing operation={operation}")


def _validate_disclosures(rows: list[dict[str, Any]]) -> None:
    """공시 고유번호·회사코드·접수일을 보존해 PIT 결합 근거를 보장한다."""

    for row in rows:
        receipt = str(row.get("rcept_no", ""))
        corp_code = str(row.get("corp_code", ""))
        receipt_date = str(row.get("rcept_dt", ""))
        if not receipt or len(corp_code) != 8 or not corp_code.isdigit():
            raise RuntimeError("OpenDART disclosure identity is invalid")
        if len(receipt_date) != 8 or not receipt_date.isdigit():
            raise RuntimeError("OpenDART rcept_dt is invalid")


class ModelRawCollector:
    """source별 안전한 동시성과 월별 checkpoint를 적용하는 Raw 수집기다."""

    def __init__(
        self,
        storage: BlobStorage,
        *,
        container: str,
        manifest: CoverageManifest,
        start_date: date,
        end_date: date,
        benchmark: bool = False,
        company_limit: int | None = None,
    ) -> None:
        self.storage = storage
        self.container = container
        self.manifest = manifest
        self.start_date = start_date
        self.end_date = end_date
        self.benchmark = benchmark
        self.company_limit = company_limit
        self.metrics = {
            name: SourceMetrics(name) for name in ("krx", "ecos-bok", "opendart")
        }
        self.concurrency = {
            "krx": _bounded_env("KRX_MAX_CONCURRENCY", 4, 16),
            "ecos-bok": _bounded_env("ECOS_MAX_CONCURRENCY", 2, 4),
            # OpenDART는 일일 제한과 020 응답 특성 때문에 기본값을 직렬로 둔다.
            "opendart": _bounded_env("OPENDART_MAX_CONCURRENCY", 1, 4),
        }
        self.checkpoint_every = _bounded_env("MODEL_RAW_CHECKPOINT_EVERY", 5, 100)
        self._thread_local = threading.local()
        self._dart_rate_lock = threading.Lock()
        self._dart_last_request_at = 0.0
        self._dart_interval_seconds = float(
            os.getenv("OPENDART_MIN_INTERVAL_SECONDS", "0.25")
        )

    def _progress(self, source: str, processed: int, total: int, label: str) -> None:
        metrics = self.metrics[source].as_dict()
        elapsed = metrics["elapsed_seconds"]
        rate = processed / max(elapsed, 0.000001)
        eta = (total - processed) / rate if rate else 0
        print(
            f"[{source.upper()}] {label} chunks={processed}/{total} rows={metrics['rows']:,} "
            f"download={metrics['rows_per_second']:,.1f} rows/s "
            f"upload={metrics['upload_mb_per_second']:,.2f} MB/s "
            f"elapsed={timedelta(seconds=int(elapsed))} ETA={timedelta(seconds=int(eta))}"
        )

    def _krx_client(self) -> KrxClient:
        client = getattr(self._thread_local, "krx_client", None)
        if client is None:
            client = KrxClient(
                os.getenv("KRX_AUTH_KEY", ""),
                base_url=os.getenv("KRX_BASE_URL", "https://data-dbg.krx.co.kr/svc/apis"),
                timeout_seconds=float(os.getenv("KRX_TIMEOUT_SECONDS", "10")),
            )
            self._thread_local.krx_client = client
        return client

    def _ecos_client(self) -> EcosClient:
        client = getattr(self._thread_local, "ecos_client", None)
        if client is None:
            client = EcosClient(
                os.getenv("ECOS_API_KEY", ""),
                timeout_seconds=float(os.getenv("ECOS_TIMEOUT_SECONDS", "10")),
                page_size=1000,
            )
            self._thread_local.ecos_client = client
        return client

    def _dart_client(self) -> OpenDartClient:
        client = getattr(self._thread_local, "dart_client", None)
        if client is None:
            client = OpenDartClient(
                os.getenv("OPENDART_API_KEY", ""),
                timeout_seconds=float(os.getenv("OPENDART_TIMEOUT_SECONDS", "10")),
                min_interval_seconds=self._dart_interval_seconds,
                rate_limiter=self._wait_for_dart_slot,
            )
            self._thread_local.dart_client = client
        return client

    def _wait_for_dart_slot(self) -> None:
        """worker 수와 무관하게 OpenDART 전체 요청 시작 간격을 한 곳에서 제한한다."""

        with self._dart_rate_lock:
            remaining = self._dart_interval_seconds - (
                time.monotonic() - self._dart_last_request_at
            )
            if remaining > 0:
                time.sleep(remaining)
            self._dart_last_request_at = time.monotonic()

    def _krx_date(self, base_date: date) -> dict[str, tuple[int, int]]:
        client = self._krx_client()
        writer = RawBlobWriter(self.storage, container=self.container, source="krx")
        result: dict[str, tuple[int, int]] = {}
        for operation in OPERATIONS:
            started = time.monotonic()
            rows = client.fetch(operation, base_date.strftime("%Y%m%d"))
            self.metrics["krx"].add(api_calls=1, download_seconds=time.monotonic() - started)
            _validate_krx(operation, rows, base_date)
            created = uploaded = 0
            if rows:
                upload_started = time.monotonic()
                blob, _batch = writer.upload_items(
                    dataset=operation.dataset,
                    operation=operation.name,
                    items=rows,
                    partition_date=base_date,
                )
                upload_elapsed = time.monotonic() - upload_started
                created = int(blob.created)
                uploaded = blob.size if blob.created else 0
                self.metrics["krx"].add(
                    upload_seconds=upload_elapsed,
                    uploaded_bytes=uploaded,
                    new_blobs=created,
                    reused_blobs=int(not blob.created),
                )
            result[operation.name] = (len(rows), created)
            self.metrics["krx"].add(rows=len(rows))
        return result

    def _bootstrap_krx_dates(self) -> None:
        """legacy Raw에서 실제 확인된 거래일만 KRX 완료 checkpoint로 복원한다.

        KOSPI 지수는 일별 객체가 작고 BAS_DD가 있어 anchor로 사용한다. 날짜형 operation의
        월별 객체 수가 anchor와 모두 같고 두 Master snapshot도 존재할 때만 그 월의 anchor
        날짜를 전체 operation 완료로 승격한다. 일부 날짜 Blob만 있는 월은 존재한 날짜만
        복원되므로 나머지 평일은 provider 수집 대상으로 남는다.
        """

        requested_months = {
            value.strftime("%Y-%m")
            for value in _month_starts(self.start_date, self.end_date)
        }
        months_by_operation: dict[str, dict[str, list[str]]] = {}
        for operation in OPERATIONS:
            prefix = f"krx/{operation.dataset}/operation={operation.name}/"
            paths = [
                path for path in self.storage.list_paths(self.container, prefix=prefix)
                if path.endswith(".jsonl.gz")
            ]
            grouped: dict[str, list[str]] = defaultdict(list)
            for path in paths:
                if match := MONTH_PATTERN.search(path):
                    month = f"{match.group(1)}-{match.group(2)}"
                    if month in requested_months:
                        grouped[month].append(path)
            months_by_operation[operation.name] = grouped

        anchor_name = "kospi_dd_trd"
        dated_operations = [
            operation for operation in OPERATIONS if operation.dataset != "stock_master"
        ]
        master_operations = [
            operation for operation in OPERATIONS if operation.dataset == "stock_master"
        ]
        for month, anchor_paths in months_by_operation[anchor_name].items():
            existing_dates = set.intersection(
                *(
                    {
                        value
                        for value in self.manifest.completed(
                            "krx", operation.dataset, operation.name
                        )
                        if value.startswith(month + "-")
                    }
                    for operation in OPERATIONS
                )
            )
            expected_object_count = len(anchor_paths)
            date_counts_match = all(
                len(months_by_operation[operation.name].get(month, []))
                == expected_object_count
                for operation in dated_operations
            )
            masters_exist = all(
                bool(months_by_operation[operation.name].get(month, []))
                for operation in master_operations
            )
            if (
                existing_dates
                and len(existing_dates) == expected_object_count
                and date_counts_match
                and masters_exist
            ):
                continue
            anchor_dates = {
                value
                for path in anchor_paths
                if (value := _raw_krx_date(
                    self.storage.download_bytes(self.container, path)
                )) is not None
            }
            if not anchor_dates:
                continue
            expected_count = len(anchor_dates)
            dates_match = all(
                len(months_by_operation[operation.name].get(month, [])) == expected_count
                for operation in dated_operations
            )
            if not dates_match or not masters_exist:
                continue
            for value in anchor_dates:
                for operation in OPERATIONS:
                    self.manifest.mark(
                        source="krx",
                        dataset=operation.dataset,
                        operation=operation.name,
                        partition=value.isoformat(),
                        rows=0,
                        blob_count=0,
                    )

    def collect_krx(self) -> None:
        """과거 완료 월을 Blob 경로로 복원하고 누락 평일만 날짜 병렬 수집한다."""

        source = "krx"
        self.metrics[source].reset_clock()
        self._bootstrap_krx_dates()
        self.manifest.save()
        months = _month_starts(self.start_date, self.end_date)
        processed_months = 0
        for month in months:
            month_key = month.strftime("%Y-%m")
            start, end = _month_range(month, self.start_date, self.end_date)
            dates = _weekdays(start, end)
            missing = [
                value for value in dates
                if not all(
                    self.manifest.is_completed(
                        source, operation.dataset, operation.name, value.isoformat()
                    )
                    for operation in OPERATIONS
                )
            ]
            self.metrics[source].add(skipped_partitions=len(dates) - len(missing))
            with ThreadPoolExecutor(
                max_workers=self.concurrency[source], thread_name_prefix="krx-fetch"
            ) as executor:
                futures = {executor.submit(self._krx_date, value): value for value in missing}
                completed_since_save = 0
                for future in as_completed(futures):
                    value = futures[future]
                    result = future.result()
                    for operation in OPERATIONS:
                        rows, blobs = result[operation.name]
                        self.manifest.mark(
                            source=source,
                            dataset=operation.dataset,
                            operation=operation.name,
                            partition=value.isoformat(),
                            rows=rows,
                            blob_count=blobs,
                        )
                    self.metrics[source].add(completed_partitions=1)
                    completed_since_save += 1
                    if completed_since_save >= self.checkpoint_every:
                        self.manifest.save()
                        completed_since_save = 0
            self.manifest.save()
            processed_months += 1
            self._progress(source, processed_months, len(months), month_key)

    def _ecos_partition(self, series_name: str, month: date) -> tuple[str, int, int]:
        series = ECOS_SERIES[series_name]
        start, end = _month_range(month, self.start_date, self.end_date)
        started = time.monotonic()
        rows = self._ecos_client().observations(series, start, end)
        self.metrics["ecos-bok"].add(api_calls=1, download_seconds=time.monotonic() - started)
        _validate_ecos(rows, cycle=series.cycle, operation=series_name)
        created = 0
        if rows:
            writer = RawBlobWriter(self.storage, container=self.container, source="ecos-bok")
            upload_started = time.monotonic()
            blob, _batch = writer.upload_items(
                dataset="ecos", operation=series_name, items=rows, partition_date=month
            )
            created = int(blob.created)
            self.metrics["ecos-bok"].add(
                upload_seconds=time.monotonic() - upload_started,
                uploaded_bytes=blob.size if blob.created else 0,
                new_blobs=created,
                reused_blobs=int(not blob.created),
            )
        self.metrics["ecos-bok"].add(rows=len(rows))
        return series_name, len(rows), created

    def collect_ecos(self) -> None:
        """시계열×월 batch를 ECOS 제한 안에서 병렬 조회하고 최대 page size를 사용한다."""

        source = "ecos-bok"
        self.metrics[source].reset_clock()
        current_month = self.end_date.strftime("%Y-%m")
        for name in ECOS_SERIES:
            self.manifest.bootstrap_historical_months(
                source=source,
                dataset="ecos",
                operation=name,
                prefix=f"ecos-bok/ecos/operation={name}/",
                current_month=current_month,
            )
        tasks = [
            (name, month, _range_partition(month, self.start_date, self.end_date))
            for name in ECOS_SERIES
            for month in _month_starts(self.start_date, self.end_date)
            if not self.manifest.is_completed(
                source,
                "ecos",
                name,
                _range_partition(month, self.start_date, self.end_date),
            )
        ]
        total = len(tasks)
        if not tasks:
            print("[ECOS-BOK] no missing partitions")
            return
        with ThreadPoolExecutor(
            max_workers=self.concurrency[source], thread_name_prefix="ecos-fetch"
        ) as executor:
            future_map = {
                executor.submit(self._ecos_partition, name, month): (name, month, partition)
                for name, month, partition in tasks
            }
            for index, future in enumerate(as_completed(future_map), start=1):
                name, month, partition = future_map[future]
                _, rows, blobs = future.result()
                self.manifest.mark(
                    source=source,
                    dataset="ecos",
                    operation=name,
                    partition=partition,
                    rows=rows,
                    blob_count=blobs,
                )
                self.metrics[source].add(completed_partitions=1)
                if index % self.checkpoint_every == 0:
                    self.manifest.save()
                self._progress(source, index, total, f"{name}:{month:%Y-%m}")
        self.manifest.save()

    def _corp_codes(self) -> list[str]:
        """당일 corpCode를 한 번만 수집하고 상장사 8자리 corp_code를 메모리에만 유지한다."""

        source = "opendart"
        snapshot_date = date.today()
        partition = snapshot_date.isoformat()
        prefix = f"opendart/corp_code/{snapshot_date:%Y/%m/%d}/"
        paths = sorted(self.storage.list_paths(self.container, prefix=prefix))
        if self.manifest.is_completed(source, "corp_code", "corp_code", partition) and paths:
            content = self.storage.download_bytes(self.container, paths[-1])
            self.metrics[source].add(skipped_partitions=1)
        else:
            started = time.monotonic()
            content = self._dart_client().download_corp_codes()
            self.metrics[source].add(api_calls=1, download_seconds=time.monotonic() - started)
            upload_started = time.monotonic()
            blob = OpenDartRawWriter(self.storage, container=self.container).upload_bytes(
                dataset="corp_code",
                content=content,
                partition_date=snapshot_date,
                extension="zip",
                content_type="application/zip",
            )
            self.metrics[source].add(
                upload_seconds=time.monotonic() - upload_started,
                uploaded_bytes=blob.size if blob.created else 0,
                new_blobs=int(blob.created),
                reused_blobs=int(not blob.created),
                completed_partitions=1,
            )
            self.manifest.mark(
                source=source,
                dataset="corp_code",
                operation="corp_code",
                partition=partition,
                rows=0,
                blob_count=int(blob.created),
            )
            self.manifest.save()
        records = parse_corp_code_zip(content)
        listed = [record.corp_code for record in records if record.stock_code]
        if self.company_limit is not None:
            listed = listed[: max(1, self.company_limit)]
        if not listed:
            raise RuntimeError("OpenDART listed corp codes are empty")
        # corp_code와 stock_code를 문자열로만 다뤄 선행 0을 보존한다.
        if any(len(code) != 8 or not code.isdigit() for code in listed):
            raise RuntimeError("OpenDART corp_code validation failed")
        return listed

    @staticmethod
    def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
        for start in range(0, len(values), size):
            yield values[start : start + size]

    def _dart_financial(
        self, codes: list[str], year: int, report_code: str
    ) -> tuple[int, int, bool]:
        started = time.monotonic()
        response = self._dart_client().financials_multi(codes, str(year), report_code)
        self.metrics["opendart"].add(api_calls=1, download_seconds=time.monotonic() - started)
        rows = response.payload.get("list", [])
        if not isinstance(rows, list):
            raise RuntimeError("OpenDART financial list must be an array")
        for row in rows:
            stock_code = str(row.get("stock_code", "")).strip()
            if stock_code and (len(stock_code) != 6 or not stock_code.isdigit()):
                raise RuntimeError("OpenDART financial stock_code is invalid")
            if str(row.get("bsns_year", year)) != str(year):
                raise RuntimeError("OpenDART financial business year mismatch")
            if str(row.get("reprt_code", report_code)) != report_code:
                raise RuntimeError("OpenDART financial report code mismatch")
        period_month, period_day = REPORT_PERIOD_END[report_code]
        period_end = date(year, period_month, period_day)
        created = 0
        if rows:
            upload_started = time.monotonic()
            blob = OpenDartRawWriter(self.storage, container=self.container).upload_bytes(
                dataset="financial_multi",
                content=response.content,
                partition_date=period_end,
                extension="json",
                content_type="application/json",
            )
            created = int(blob.created)
            self.metrics["opendart"].add(
                upload_seconds=time.monotonic() - upload_started,
                uploaded_bytes=blob.size if blob.created else 0,
                new_blobs=created,
                reused_blobs=int(not blob.created),
            )
        self.metrics["opendart"].add(rows=len(rows))
        return (
            len(rows),
            created,
            _financial_checkpoint_allowed(
                str(response.payload.get("status", "")), period_end
            ),
        )

    def _dart_disclosure(self, month: date, corp_cls: str) -> tuple[int, int, int]:
        """공시 page를 한 장씩 검증·업로드하고 진행률과 resume page를 기록한다."""

        start, end = _month_range(month, self.start_date, self.end_date)
        partition = f"{_range_partition(month, self.start_date, self.end_date)}-{corp_cls}"
        resume_page, total_rows, new_blobs = self.manifest.partial_progress(
            "opendart", "disclosure_market", "disclosure_market", partition
        )
        responses = iter(self._dart_client().iter_disclosures_market(
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            corp_cls=corp_cls,
            start_page=resume_page + 1,
        ))
        writer = OpenDartRawWriter(self.storage, container=self.container)
        page_count = fetched_rows = 0
        while True:
            started = time.monotonic()
            try:
                response = next(responses)
            except StopIteration:
                break
            page_count += 1
            page_no = resume_page + page_count
            self.metrics["opendart"].add(
                api_calls=1, download_seconds=time.monotonic() - started
            )
            rows = response.payload.get("list", [])
            if not isinstance(rows, list):
                raise RuntimeError("OpenDART disclosure list must be an array")
            _validate_disclosures(rows)
            total_rows += len(rows)
            fetched_rows += len(rows)
            if rows:
                partition_date = date.fromisoformat(
                    f"{str(rows[0]['rcept_dt'])[:4]}-{str(rows[0]['rcept_dt'])[4:6]}-{str(rows[0]['rcept_dt'])[6:]}"
                )
                upload_started = time.monotonic()
                blob = writer.upload_bytes(
                    dataset="disclosure_market",
                    content=response.content,
                    partition_date=partition_date,
                    extension="json",
                    content_type="application/json",
                )
                new_blobs += int(blob.created)
                self.metrics["opendart"].add(
                    upload_seconds=time.monotonic() - upload_started,
                    uploaded_bytes=blob.size if blob.created else 0,
                    new_blobs=int(blob.created),
                    reused_blobs=int(not blob.created),
                )
            self.manifest.mark_partial_page(
                source="opendart",
                dataset="disclosure_market",
                operation="disclosure_market",
                partition=partition,
                page_no=page_no,
                rows=total_rows,
                blob_count=new_blobs,
            )
            if page_no % self.checkpoint_every == 0:
                self.manifest.save()
            try:
                total_page = max(1, int(response.payload.get("total_page", page_no)))
            except (TypeError, ValueError):
                total_page = page_no
            if page_count == 1 or page_no % 10 == 0 or page_no >= total_page:
                print(
                    "[OPENDART] disclosure page "
                    f"window={start.isoformat()}..{end.isoformat()} market={corp_cls} "
                    f"page={page_no}/{total_page} rows={total_rows:,} "
                    f"new_blobs={new_blobs:,}"
                )
        self.metrics["opendart"].add(rows=fetched_rows)
        return total_rows, new_blobs, page_count

    def collect_opendart(self) -> None:
        """회사 100개 batch와 월별 공시 window를 제한된 worker로 수집한다."""

        source = "opendart"
        self.metrics[source].reset_clock()
        codes = self._corp_codes()
        tasks: list[tuple[str, str, Callable[[], tuple[int, int, bool]]]] = []
        for year in range(self.start_date.year, self.end_date.year + 1):
            for report_code in REPORT_CODES:
                month, day = REPORT_PERIOD_END[report_code]
                period_end = date(year, month, day)
                if not self.start_date <= period_end <= self.end_date:
                    continue
                for chunk in self._chunks(codes, 100):
                    digest = hashlib.sha256(",".join(chunk).encode()).hexdigest()[:16]
                    partition = f"{year}-{report_code}-{digest}"
                    if self.manifest.is_completed(
                        source, "financial_multi", "financial_multi", partition
                    ):
                        self.metrics[source].add(skipped_partitions=1)
                        continue
                    tasks.append(
                        (
                            "financial_multi",
                            partition,
                            lambda chunk=chunk, year=year, code=report_code: self._dart_financial(
                                chunk, year, code
                            ),
                        )
                    )
        for month in _month_starts(self.start_date, self.end_date):
            for corp_cls in ("Y", "K"):
                partition = (
                    f"{_range_partition(month, self.start_date, self.end_date)}-{corp_cls}"
                )
                if self.manifest.is_completed(
                    source, "disclosure_market", "disclosure_market", partition
                ):
                    self.metrics[source].add(skipped_partitions=1)
                    continue
                tasks.append(
                    (
                        "disclosure_market",
                        partition,
                        lambda month=month, corp_cls=corp_cls: self._dart_disclosure(
                            month, corp_cls
                        )[:2] + (True,),
                    )
                )
        if not tasks:
            print("[OPENDART] no missing partitions")
            return
        with ThreadPoolExecutor(
            max_workers=self.concurrency[source], thread_name_prefix="opendart-fetch"
        ) as executor:
            future_map = {
                executor.submit(call): (dataset, partition)
                for dataset, partition, call in tasks
            }
            for index, future in enumerate(as_completed(future_map), start=1):
                dataset, partition = future_map[future]
                rows, blobs, checkpoint_allowed = future.result()
                if checkpoint_allowed:
                    self.manifest.mark(
                        source=source,
                        dataset=dataset,
                        operation=dataset,
                        partition=partition,
                        rows=rows,
                        blob_count=blobs,
                    )
                    self.metrics[source].add(completed_partitions=1)
                else:
                    print(f"[OPENDART] pending late filing partition={partition} status=013")
                if index % self.checkpoint_every == 0:
                    self.manifest.save()
                self._progress(source, index, len(tasks), partition)
        self.manifest.save()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect resumable model Raw data to Azure Blob")
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--source", action="append", choices=("krx", "ecos", "opendart"),
        help="특정 source만 수집한다. 여러 번 지정할 수 있다.",
    )
    parser.add_argument("--benchmark", action="store_true", help="성능 수치를 요약 보고서에 표시한다.")
    parser.add_argument(
        "--company-limit", type=int,
        help="smoke test용 OpenDART 상장사 제한. 전체 운영 수집에서는 사용하지 않는다.",
    )
    return parser


def _write_reports(
    *, collector: ModelRawCollector, selected: list[str], started_at: datetime
) -> dict[str, Any]:
    """모델 개발자가 바로 사용할 수 있는 성능 요약과 데이터 인벤토리를 생성한다."""

    finished_at = datetime.now(timezone.utc)
    metrics = {name: value.as_dict() for name, value in collector.metrics.items()}
    total_rows = sum(int(value["rows"]) for value in metrics.values())
    total_seconds = max((finished_at - started_at).total_seconds(), 0.000001)
    payload = {
        "generated_at": finished_at.isoformat(),
        "range": {"start": collector.start_date.isoformat(), "end": collector.end_date.isoformat()},
        "selected_sources": selected,
        "benchmark": collector.benchmark,
        "company_limit": collector.company_limit,
        "concurrency": collector.concurrency,
        "batch": {
            "krx": "date x 7 full-market endpoints",
            "ecos": "series x calendar month; page_size=1000",
            "opendart_financial": "100 companies x report period",
            "opendart_disclosure": "market x calendar month; page_size=100",
        },
        "blob_upload": {
            "format": "canonical JSONL gzip (KRX/ECOS), provider bytes (OpenDART)",
            "sdk_max_concurrency": collector.storage.upload_max_concurrency,
            "content_addressed": True,
        },
        "sources": metrics,
        "total_rows": total_rows,
        "total_elapsed_seconds": round(total_seconds, 3),
        "average_rows_per_second": round(total_rows / total_seconds, 3),
        "bottleneck": max(
            metrics.values(), key=lambda value: float(value["active_seconds"])
        )["source"],
        "additional_optimization": [
            "OpenDART quota가 상향된 환경에서만 OPENDART_MAX_CONCURRENCY를 2 이상으로 조정",
            "신규 Raw metadata에 partition_date를 기록해 legacy bootstrap 검증 비용 축소",
        ],
    }
    SUMMARY_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = [
        "# Model Raw Collection Summary", "",
        f"- 테스트 기간: {collector.start_date} ~ {collector.end_date}",
        f"- 총 실행 시간: {payload['total_elapsed_seconds']}초",
        f"- 전체 신규/검증 row: {total_rows:,}",
        f"- 평균 처리량: {payload['average_rows_per_second']:,.2f} rows/s",
        f"- 병목 source: {payload['bottleneck']}",
        f"- OpenDART company limit: {collector.company_limit or '없음(전체)'}",
        "", "## Source별 성능", "",
        "| Source | Concurrency | API calls | Rows | Download(s) | Upload(s) | Rows/s | Upload MB/s | New blobs | Skipped |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, value in metrics.items():
        markdown.append(
            f"| {name} | {collector.concurrency[name]} | {value['api_calls']:,} | "
            f"{value['rows']:,} | {value['download_seconds']:,.3f} | "
            f"{value['upload_seconds']:,.3f} | {value['rows_per_second']:,.2f} | "
            f"{value['upload_mb_per_second']:,.2f} | {value['new_blobs']:,} | "
            f"{value['skipped_partitions']:,} |"
        )
    markdown.extend([
        "", "## 적용 방식", "",
        "- 월/기간 partition 단위로 누락 작업만 계산하고 source별 bounded worker를 사용한다.",
        "- KRX·ECOS는 canonical JSONL gzip, OpenDART는 provider 원문 bytes를 content hash 경로로 저장한다.",
        "- 성공 partition만 `_manifests/model_raw_coverage.json`에 기록하며 실제 Blob prefix와 교차검증한다.",
        "- 수집과 업로드가 worker 안에서 연속 실행되어 다른 worker의 네트워크 대기와 겹친다.",
        "- 429/5xx는 각 공통 client의 제한된 exponential backoff를 사용한다.",
    ])
    SUMMARY_MARKDOWN_PATH.write_text("\n".join(markdown) + "\n", encoding="utf-8")

    inventory = """# 정도영 모델 데이터 인벤토리

## 저장 위치와 사용 우선순위

모델 학습 원본의 Source of Truth는 Azure Blob `raw` 컨테이너다. `market_stock_prices`는
화면 조회·백테스트 서빙용 PostgreSQL 테이블이며 대규모 학습 원본으로 사용하지 않는다.

| Source | Blob prefix | 핵심 식별자/날짜 | 형식 | 모델 용도 |
|---|---|---|---|---|
| KRX | `krx/stock_price`, `krx/stock_master`, `krx/market_index` | `BAS_DD`, 6자리 종목코드 | JSONL.gz | OHLCV·거래대금·시총·시장지수 |
| ECOS | `ecos-bok/ecos/operation=<series>` | `TIME`, `DATA_VALUE` | JSONL.gz | 기준금리·USD/KRW·CPI·국고채 3Y/10Y |
| OpenDART | `opendart/corp_code`, `financial_multi`, `disclosure_market` | `corp_code`, `rcept_no`, `rcept_dt` | ZIP/JSON 원문 | 기업 매핑·재무·공시 이벤트 |
| data.go.kr | 기존 `data-go-kr/...` | dataset별 `basDt` | JSONL.gz | 기존 보조 금융 Raw(이번 수집기는 변경하지 않음) |

## Point-in-Time 주의사항

- OpenDART 재무값은 결산일이 아니라 해당 보고서의 실제 `rcept_dt` 이후에만 Feature로 결합한다.
- ECOS 월간 CPI는 공표 지연을 반영한 `available_at` 정책을 적용한 Processed/Feature를 사용한다.
- 모든 종목·회사 코드는 숫자로 변환하지 말고 문자열로 읽어 선행 0을 보존한다.
- 결측·휴장일을 0으로 채우지 않는다. 거래일 기준 KRX 시계열에 발표 시점이 지난 거시값만 결합한다.

## 재현과 lineage

Raw 객체는 payload/content hash 경로라 같은 응답의 재실행이 새 객체를 만들지 않는다.
수집 범위와 완료 partition은 `raw/_manifests/model_raw_coverage.json`, 실행 성능은
`data/reports/MODEL_RAW_COLLECTION_SUMMARY.{json,md}`에서 확인한다.
"""
    INVENTORY_PATH.write_text(inventory, encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    """환경 검증 후 선택한 source를 수집하고 성능·handoff 보고서를 갱신한다."""

    load_dotenv(REPOSITORY_ROOT / ".env", override=False)
    args = _parser().parse_args(argv)
    if args.start_date > args.end_date:
        raise SystemExit("--start-date must not be after --end-date")
    if args.start_date < DEFAULT_START_DATE:
        raise SystemExit("--start-date must be on or after 2018-01-01")
    selected = args.source or ["krx", "ecos", "opendart"]
    required = {
        "krx": "KRX_AUTH_KEY",
        "ecos": "ECOS_API_KEY",
        "opendart": "OPENDART_API_KEY",
    }
    missing = [required[name] for name in selected if not os.getenv(required[name], "").strip()]
    if missing:
        raise RuntimeError("model Raw collection missing environment variables: " + ", ".join(missing))

    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    storage.service_client.get_container_client(container).get_container_properties()
    manifest = CoverageManifest(storage, container)
    collector = ModelRawCollector(
        storage,
        container=container,
        manifest=manifest,
        start_date=args.start_date,
        end_date=args.end_date,
        benchmark=args.benchmark,
        company_limit=args.company_limit,
    )
    started_at = datetime.now(timezone.utc)
    if "krx" in selected:
        collector.collect_krx()
    if "ecos" in selected:
        collector.collect_ecos()
    if "opendart" in selected:
        collector.collect_opendart()
    payload = _write_reports(collector=collector, selected=selected, started_at=started_at)
    print(
        "MODEL RAW COLLECTION SUCCESS "
        f"range={args.start_date}..{args.end_date} rows={payload['total_rows']:,} "
        f"elapsed={payload['total_elapsed_seconds']}s report={SUMMARY_MARKDOWN_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
