"""Canonical Raw payload를 profile 기반 타입으로 정규화해 월별 Processed Parquet로 만든다."""

from __future__ import annotations

import json
import os
import tempfile
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
            if completed is not None:
                _merge_manifest_summary(summary, operation=operation, manifest=completed)
                print(
                    "PROCESSED SKIP "
                    f"dataset={dataset} operation={operation} year={year} month={month:02d} "
                    f"rows={completed.get('accepted', 0)} path={output_path}"
                )
                continue

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
                for blob in month_blobs:
                    # Blob 단위로만 메모리에 올려 2,400만 건 전체 적재를 피한다.
                    rows: list[dict[str, Any]] = []
                    for raw_record in read_blob_records(storage, raw_container, blob):
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
            "source_blobs": [item.path for item in month_blobs],
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
        print(
            "PROCESSED WRITE "
            f"dataset={dataset} operation={operation} year={year} month={month:02d} "
            f"rows={quality.accepted} rejected={quality.rejected} "
            f"conversion_errors={sum(quality.conversion_errors.values())} "
            f"path={output_path}"
        )

    return summary
