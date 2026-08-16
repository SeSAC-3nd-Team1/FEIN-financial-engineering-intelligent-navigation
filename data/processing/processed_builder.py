"""Canonical Raw payload를 profile 기반 타입으로 정규화해 월별 Processed Parquet로 만든다."""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from processing.normalize import build_operation_contract, normalize_payload
from processing.quality import QualityResult, validate_payload
from processing.raw_reader import RawBlob, list_raw_blobs, read_blob_records


def _pa_type(dtype: str) -> pa.DataType:
    return {
        "date": pa.date32(),
        "integer": pa.int64(),
        "number": pa.float64(),
        "string": pa.string(),
    }[dtype]


def _duration(seconds: float | None) -> str:
    """터미널 진행 로그에서 읽기 쉬운 HH:MM:SS 형식으로 시간을 표시한다."""

    if seconds is None or seconds < 0:
        return "--:--:--"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _eta(elapsed: float, done: int, total: int) -> float | None:
    """현재 처리 속도가 유지된다는 가정으로 남은 시간을 계산한다."""

    if done <= 0 or elapsed <= 0:
        return None
    if done >= total:
        return 0.0
    return elapsed * (total - done) / done


def processed_path(
    dataset: str,
    operation: str,
    year: int,
    month: int,
    schema_version: str,
) -> str:
    return (
        f"{dataset}/operation={operation}/schema=v{schema_version}/"
        f"year={year:04d}/month={month:02d}/part-00000.parquet"
    )


def quality_path(
    dataset: str,
    operation: str,
    year: int,
    month: int,
    schema_version: str,
) -> str:
    return (
        f"_quality/{dataset}/operation={operation}/schema=v{schema_version}/"
        f"year={year:04d}/month={month:02d}/manifest.json"
    )


def _group_monthly(
    blobs: list[RawBlob],
) -> dict[tuple[str, int, int], list[RawBlob]]:
    grouped: dict[tuple[str, int, int], list[RawBlob]] = defaultdict(list)
    for blob in blobs:
        grouped[(blob.operation, blob.year, blob.month)].append(blob)
    return dict(grouped)


def _merge_manifest_summary(
    summary: dict[str, Any],
    *,
    operation: str,
    manifest: dict[str, Any],
) -> None:
    """신규 생성과 resume skip이 동일한 집계 결과를 만들도록 manifest를 누적한다."""

    accepted = int(manifest.get("accepted", 0))
    rejected = int(manifest.get("rejected", 0))
    summary["files"] += 1
    summary["accepted"] += accepted
    summary["rejected"] += rejected
    for field, count in manifest.get("conversion_errors", {}).items():
        summary["conversion_errors"][field] = (
            summary["conversion_errors"].get(field, 0) + int(count)
        )

    operation_summary = summary["operations"].setdefault(
        operation,
        {"files": 0, "accepted": 0, "rejected": 0},
    )
    operation_summary["files"] += 1
    operation_summary["accepted"] += accepted
    operation_summary["rejected"] += rejected


def _load_completed_manifest(
    storage,
    *,
    container: str,
    output_path: str,
    manifest_path: str,
    dataset: str,
    operation: str,
    year: int,
    month: int,
    schema_version: str,
) -> dict[str, Any] | None:
    """Parquet과 품질 manifest가 모두 존재하고 계약이 일치할 때만 완료 partition으로 인정한다."""

    if not storage.exists(container, output_path) or not storage.exists(container, manifest_path):
        return None
    manifest = json.loads(storage.download_bytes(container, manifest_path))
    expected = {
        "dataset": dataset,
        "operation": operation,
        "year": year,
        "month": month,
        "schema_version": schema_version,
        "output_path": output_path,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        return None
    return manifest


def _expected_month_rows(profile_operation: dict[str, Any], year: int, month: int) -> int:
    """Raw profile의 basDt 월별 분포를 ETA용 예상 행 수로 사용한다."""

    return int(profile_operation.get("month_rows", {}).get(f"{year:04d}-{month:02d}", 0))


def build_processed_dataset(
    storage,
    *,
    raw_container: str,
    processed_container: str,
    dataset: str,
    profile: dict[str, Any],
    schema_version: str = "1",
    overwrite: bool = False,
) -> dict[str, Any]:
    """한 Raw dataset의 모든 operation을 월별 Processed Parquet으로 변환한다.

    기본 실행은 resume 모드다. 동일 schema version의 Parquet과 품질 manifest가 모두 있으면
    해당 월을 다시 읽거나 변환하지 않는다. ``overwrite=True``일 때만 강제로 재생성한다.
    """

    grouped = _group_monthly(list_raw_blobs(storage, raw_container, dataset))
    summary: dict[str, Any] = {
        "dataset": dataset,
        "files": 0,
        "accepted": 0,
        "rejected": 0,
        "conversion_errors": {},
        "operations": {},
    }

    # 먼저 실행 계획을 만들면 resume된 월을 제외한 실제 남은 작업량으로 ETA를 계산할 수 있다.
    plan: list[dict[str, Any]] = []
    for (operation, year, month), month_blobs in sorted(grouped.items()):
        op_profile = profile["operations"].get(operation)
        if not op_profile:
            raise RuntimeError(f"profile missing operation: {dataset}/{operation}")

        output_path = processed_path(
            dataset,
            operation,
            year,
            month,
            schema_version,
        )
        manifest_path = quality_path(
            dataset,
            operation,
            year,
            month,
            schema_version,
        )
        completed = None
        if not overwrite:
            completed = _load_completed_manifest(
                storage,
                container=processed_container,
                output_path=output_path,
                manifest_path=manifest_path,
                dataset=dataset,
                operation=operation,
                year=year,
                month=month,
                schema_version=schema_version,
            )

        plan.append(
            {
                "operation": operation,
                "year": year,
                "month": month,
                "blobs": month_blobs,
                "profile": op_profile,
                "output_path": output_path,
                "manifest_path": manifest_path,
                "completed": completed,
                "expected_rows": _expected_month_rows(op_profile, year, month),
                "compressed_bytes": sum(item.size for item in month_blobs),
            }
        )

    pending = [item for item in plan if item["completed"] is None]
    pending_total_rows = sum(int(item["expected_rows"]) for item in pending)
    pending_total_bytes = sum(int(item["compressed_bytes"]) for item in pending)
    pending_done_rows = 0
    pending_done_bytes = 0
    pending_done_partitions = 0
    started = time.monotonic()

    print(
        "PROCESSED PLAN "
        f"dataset={dataset} partitions={len(plan)} pending={len(pending)} "
        f"resume={len(plan) - len(pending)} expected_rows={pending_total_rows:,} "
        f"compressed_bytes={pending_total_bytes:,}"
    )

    for partition_index, item in enumerate(plan, start=1):
        operation = str(item["operation"])
        year = int(item["year"])
        month = int(item["month"])
        month_blobs = item["blobs"]
        op_profile = item["profile"]
        output_path = str(item["output_path"])
        manifest_path = str(item["manifest_path"])
        completed = item["completed"]

        if completed is not None:
            _merge_manifest_summary(summary, operation=operation, manifest=completed)
            print(
                "PROCESSED SKIP "
                f"dataset={dataset} partition={partition_index}/{len(plan)} "
                f"operation={operation} year={year} month={month:02d} "
                f"rows={completed.get('accepted', 0)} path={output_path}"
            )
            continue

        print(
            "PROCESSED START "
            f"dataset={dataset} partition={partition_index}/{len(plan)} "
            f"operation={operation} year={year} month={month:02d} "
            f"blobs={len(month_blobs)} expected_rows={int(item['expected_rows']):,}"
        )

        contract = build_operation_contract(op_profile, dataset, operation)
        output_names = [name for name, _ in contract.values()]
        if len(output_names) != len(set(output_names)):
            raise RuntimeError(
                f"canonical column collision: {dataset}/{operation}: {output_names}"
            )

        schema = pa.schema(
            [
                pa.field(name, _pa_type(dtype), nullable=True)
                for name, dtype in contract.values()
            ]
            + [
                pa.field("_payload_hash", pa.string(), nullable=True),
                pa.field("_collected_at", pa.string(), nullable=True),
                pa.field("_source_blob", pa.string(), nullable=False),
            ]
        )

        quality = QualityResult()
        with tempfile.TemporaryDirectory(prefix="fein-processed-") as directory:
            local_path = Path(directory) / "part-00000.parquet"
            writer = pq.ParquetWriter(local_path, schema=schema, compression="zstd")
            try:
                for blob_index, blob in enumerate(month_blobs, start=1):
                    # Blob 단위로만 메모리에 올려 2,400만 건 전체 적재를 피한다.
                    rows: list[dict[str, Any]] = []
                    blob_seen = 0
                    for raw_record in read_blob_records(storage, raw_container, blob):
                        blob_seen += 1
                        reason = validate_payload(
                            raw_record.payload,
                            dataset,
                            operation,
                        )
                        if reason:
                            quality.reject(reason)
                            continue

                        normalized, conversion_errors = normalize_payload(
                            raw_record.payload,
                            contract,
                        )
                        for field in conversion_errors:
                            quality.conversion_error(field)

                        normalized.update(
                            {
                                "_payload_hash": raw_record.payload_hash,
                                "_collected_at": raw_record.collected_at,
                                "_source_blob": raw_record.source_blob,
                            }
                        )
                        rows.append(normalized)

                    if rows:
                        writer.write_table(pa.Table.from_pylist(rows, schema=schema))
                        quality.accepted += len(rows)

                    pending_done_rows += blob_seen
                    pending_done_bytes += blob.size
                    elapsed = time.monotonic() - started
                    if pending_total_rows > 0:
                        progress_done = min(pending_done_rows, pending_total_rows)
                        progress_total = pending_total_rows
                    else:
                        progress_done = pending_done_bytes
                        progress_total = pending_total_bytes
                    remaining = _eta(elapsed, progress_done, progress_total)
                    percent = (
                        progress_done / progress_total * 100.0
                        if progress_total > 0
                        else 100.0
                    )
                    speed = pending_done_rows / elapsed if elapsed > 0 else 0.0
                    print(
                        "PROCESSED PROGRESS "
                        f"dataset={dataset} partition={partition_index}/{len(plan)} "
                        f"blob={blob_index}/{len(month_blobs)} "
                        f"rows={pending_done_rows:,}/{pending_total_rows:,} "
                        f"percent={percent:.1f}% speed={speed:,.0f}rows/s "
                        f"elapsed={_duration(elapsed)} eta={_duration(remaining)} "
                        f"current={operation}/{year:04d}-{month:02d}"
                    )
            finally:
                writer.close()

            result = storage.upload_file(
                processed_container,
                output_path,
                local_path,
                content_type="application/vnd.apache.parquet",
                overwrite=overwrite,
                metadata={
                    "layer": "processed",
                    "dataset": dataset,
                    "operation": operation,
                    "schema_version": schema_version,
                    "record_count": str(quality.accepted),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source": "data-go-kr",
                },
            )

        manifest = {
            "dataset": dataset,
            "operation": operation,
            "year": year,
            "month": month,
            "schema_version": schema_version,
            "source_blobs": [blob.path for blob in month_blobs],
            "accepted": quality.accepted,
            "rejected": quality.rejected,
            "reasons": quality.reasons,
            "conversion_errors": quality.conversion_errors,
            "output_path": output_path,
            "output_bytes": result.size,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "git_sha": os.getenv("GIT_SHA", "unknown"),
            "raw_immutable": True,
        }
        storage.upload_bytes(
            processed_container,
            manifest_path,
            json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
            content_type="application/json",
            overwrite=True,
        )

        _merge_manifest_summary(summary, operation=operation, manifest=manifest)
        pending_done_partitions += 1
        elapsed = time.monotonic() - started
        print(
            "PROCESSED WRITE "
            f"dataset={dataset} pending_partitions={pending_done_partitions}/{len(pending)} "
            f"operation={operation} year={year} month={month:02d} "
            f"rows={quality.accepted} rejected={quality.rejected} "
            f"conversion_errors={sum(quality.conversion_errors.values())} "
            f"elapsed={_duration(elapsed)} path={output_path}"
        )

    elapsed = time.monotonic() - started
    print(
        "PROCESSED DATASET COMPLETE "
        f"dataset={dataset} files={summary['files']} accepted={summary['accepted']:,} "
        f"rejected={summary['rejected']:,} elapsed={_duration(elapsed)}"
    )
    return summary
