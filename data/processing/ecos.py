"""ECOS canonical Raw를 검증해 versioned Processed Parquet으로 변환한다."""

from __future__ import annotations

import gzip
import io
import json
import os
from datetime import date
from typing import Any

import pandas as pd

from collectors.ecos_config import EcosSeries, get_ecos_series
from storage.paths import build_processed_path


def _availability_date(observation_date: pd.Timestamp, cycle: str) -> pd.Timestamp:
    """공표시각이 없는 월간 CPI에 보수적인 PIT 가용일을 부여한다."""

    if cycle == "M":
        # ECOS StatisticSearch에 release timestamp가 없으므로 관측월 다음 달 말 이후인
        # 두 번째 다음 달 1일에만 보이게 해 look-ahead 가능성을 보수적으로 줄인다.
        return observation_date + pd.offsets.MonthBegin(2)
    return observation_date


def normalize_ecos_records(
    records: list[dict[str, Any]], series: EcosSeries,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """ECOS envelope을 정규화하고 자연키 충돌 및 결측 품질을 집계한다."""

    accepted: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            reasons["invalid_payload"] = reasons.get("invalid_payload", 0) + 1
            continue
        try:
            time_value = str(payload["TIME"]).strip()
            observation_date = pd.to_datetime(
                time_value, format="%Y%m" if series.cycle == "M" else "%Y%m%d",
                errors="raise",
            )
            value = float(str(payload["DATA_VALUE"]).replace(",", ""))
        except (KeyError, TypeError, ValueError):
            reasons["invalid_observation"] = reasons.get("invalid_observation", 0) + 1
            continue
        if series.name in {"usd_krw", "cpi"} and value <= 0:
            reasons["non_positive_value"] = reasons.get("non_positive_value", 0) + 1
            continue
        response_unit = str(payload.get("UNIT_NAME") or series.unit).strip()
        if response_unit != series.unit:
            reasons["unit_mismatch"] = reasons.get("unit_mismatch", 0) + 1
            continue
        accepted.append({
            "series": series.name,
            "observation_date": observation_date,
            "available_at": _availability_date(observation_date, series.cycle),
            "value": value,
            "unit": response_unit,
            "source": "ecos-bok",
            "stat_code": series.stat_code,
            "item_code": series.item_code,
            "frequency": series.cycle,
            "collected_at": record.get("collectedAt"),
            "_payload_hash": record.get("payloadHash"),
            "_source_blob": record.get("_source_blob"),
        })

    frame = pd.DataFrame(accepted)
    duplicates = 0
    if not frame.empty:
        key = ["series", "observation_date"]
        duplicate_mask = frame.duplicated(key, keep=False)
        duplicates = int(duplicate_mask.sum())
        conflicts = frame.loc[duplicate_mask].groupby(key)["value"].nunique()
        if (conflicts > 1).any():
            raise RuntimeError(f"conflicting ECOS duplicates found: {series.name}")
        frame = frame.drop_duplicates(key, keep="first").sort_values("observation_date")
        if series.name == "base_rate":
            # ECOS의 동일 금리 일별 반복 행은 Raw에 보존하고 Processed에서는 변경 이벤트로 축약한다.
            frame = frame.loc[frame["value"].ne(frame["value"].shift())]
        frame = frame.reset_index(drop=True)

    quality = {
        "source_rows": len(records),
        "accepted_rows": len(frame),
        "rejected_rows": sum(reasons.values()),
        "duplicate_rows": duplicates,
        "rejection_reasons": reasons,
        "null_count": int(frame.isna().sum().sum()) if not frame.empty else 0,
        "min_observation_date": (
            frame["observation_date"].min().date().isoformat() if not frame.empty else None
        ),
        "max_observation_date": (
            frame["observation_date"].max().date().isoformat() if not frame.empty else None
        ),
    }
    return frame, quality


def read_ecos_raw(storage, container: str, series_name: str) -> list[dict[str, Any]]:
    """한 ECOS 시계열의 canonical Raw envelope과 source blob lineage를 읽는다."""

    prefix = f"ecos-bok/ecos/operation={series_name}/"
    records: list[dict[str, Any]] = []
    for path in storage.list_paths(container, prefix=prefix):
        if not path.endswith(".jsonl.gz"):
            continue
        for raw_line in gzip.decompress(storage.download_bytes(container, path)).splitlines():
            value = json.loads(raw_line)
            if not isinstance(value, dict) or not isinstance(value.get("payload"), dict):
                raise ValueError(f"invalid ECOS Raw envelope: {path}")
            records.append({**value, "_source_blob": path})
    return records


def build_ecos_processed(
    storage,
    *,
    raw_container: str,
    processed_container: str,
    series_name: str,
    schema_version: str = "1",
    overwrite: bool = False,
) -> dict[str, Any]:
    """한 시계열을 월별 Parquet과 품질 manifest로 materialize한다."""

    series = get_ecos_series(series_name)
    records = read_ecos_raw(storage, raw_container, series_name)
    frame, quality = normalize_ecos_records(records, series)
    files: list[str] = []
    if not frame.empty:
        for period, monthly in frame.groupby(frame["observation_date"].dt.to_period("M")):
            path = build_processed_path(
                "ecos", operation=series_name, schema_version=schema_version,
                partition_date=date(period.year, period.month, 1),
            )
            output = io.BytesIO()
            monthly.to_parquet(output, index=False, compression="zstd")
            storage.upload_bytes(
                processed_container, path, output.getvalue(), overwrite=overwrite,
                content_type="application/vnd.apache.parquet",
                metadata={"dataset": "ecos", "series": series_name, "schema_version": schema_version},
            )
            files.append(path)

    manifest = {
        "dataset": "ecos", "series": series_name, "schema_version": schema_version,
        "period": {
            "start": quality["min_observation_date"],
            "end": quality["max_observation_date"],
        },
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "git_sha": os.getenv("GIT_SHA", "unknown"),
        "source_blobs": sorted({str(item.get("_source_blob")) for item in records}),
        "files": files, **quality,
    }
    storage.upload_bytes(
        processed_container,
        f"_quality/ecos/operation={series_name}/schema=v{schema_version}/manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
        content_type="application/json", overwrite=True,
    )
    return manifest
