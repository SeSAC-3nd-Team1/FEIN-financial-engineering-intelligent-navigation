"""ECOS Raw 수집, Processed 변환, macro feature 생성을 실행한다."""

from __future__ import annotations

import argparse
import gzip
import json
import os
from datetime import date, datetime, timedelta

from dotenv import load_dotenv

from collectors.ecos_client import EcosClient
from collectors.ecos_config import ECOS_SERIES, get_ecos_series
from features.ecos import build_macro_features
from processing.ecos import build_ecos_processed
from storage import BlobStorage, RawBlobWriter


def parse_args() -> argparse.Namespace:
    """ECOS 파이프라인 CLI 인자를 parsing한다."""

    parser = argparse.ArgumentParser(description="한국은행 ECOS 거시경제 데이터 파이프라인")
    parser.add_argument(
        "--stage", choices=("raw", "processed", "features", "audit", "all"), default="all",
    )
    parser.add_argument("--series", action="append", choices=sorted(ECOS_SERIES))
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2021, 1, 1))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--validate-metadata", action="store_true")
    parser.add_argument("--schema-version", default="1")
    parser.add_argument("--feature-version", default="1")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _month_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """요청 기간을 Raw 월 파티션과 일치하는 닫힌 월 구간으로 나눈다."""

    ranges: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = min(end, next_month - timedelta(days=1))
        ranges.append((cursor, month_end))
        cursor = next_month
    return ranges


def _latest_raw_date(storage, container: str, series_name: str, cycle: str) -> date | None:
    """canonical Raw payload의 마지막 TIME으로 증분 시작점을 찾는다."""

    latest: date | None = None
    prefix = f"ecos-bok/ecos/operation={series_name}/"
    for path in storage.list_paths(container, prefix=prefix):
        if not path.endswith(".jsonl.gz"):
            continue
        for line in gzip.decompress(storage.download_bytes(container, path)).splitlines():
            payload = json.loads(line).get("payload", {})
            value = str(payload.get("TIME", ""))
            try:
                parsed = datetime.strptime(value, "%Y%m" if cycle == "M" else "%Y%m%d").date()
            except ValueError:
                continue
            latest = parsed if latest is None or parsed > latest else latest
    return latest


def validate_registry(client: EcosClient) -> None:
    """ECOS 항목 metadata에 registry의 item/cycle 조합이 존재하는지 확인한다."""

    cache: dict[str, list[dict[str, object]]] = {}
    for series in ECOS_SERIES.values():
        if series.stat_code not in cache:
            cache[series.stat_code] = client.statistic_items(series.stat_code)
        items = cache[series.stat_code]
        valid = any(
            str(item.get("ITEM_CODE", item.get("ITEM_CODE1", ""))) == series.item_code
            and str(item.get("CYCLE", "")) == series.cycle
            for item in items
        )
        if not valid:
            raise RuntimeError(f"ECOS registry metadata mismatch: {series.name}")


def collect_raw(
    storage, client: EcosClient, *, container: str, series_names: list[str],
    start_date: date, end_date: date, incremental: bool,
) -> list[dict[str, object]]:
    """시계열을 월별로 조회해 원문 행을 content-addressed Raw에 저장한다."""

    writer = RawBlobWriter(storage, container=container, source="ecos-bok")
    results: list[dict[str, object]] = []
    for name in series_names:
        series = get_ecos_series(name)
        effective_start = start_date
        if incremental:
            latest = _latest_raw_date(storage, container, name, series.cycle)
            if latest:
                effective_start = max(
                    effective_start,
                    (latest.replace(day=28) + timedelta(days=4)).replace(day=1)
                    if series.cycle == "M" else latest + timedelta(days=1),
                )
        for range_start, range_end in _month_ranges(effective_start, end_date):
            rows = client.observations(series, range_start, range_end)
            if not rows:
                continue
            blob, batch = writer.upload_items(
                dataset="ecos", operation=name, items=rows, partition_date=range_start,
            )
            results.append({"series": name, "path": blob.path, "rows": batch.record_count})
    return results


def audit_outputs(
    storage, *, processed_container: str, features_container: str, series_names: list[str],
) -> dict[str, object]:
    """ECOS 품질 manifest와 macro feature object 존재를 가볍게 감사한다."""

    quality = {
        name: storage.list_paths(
            processed_container, prefix=f"_quality/ecos/operation={name}/",
        )
        for name in series_names
    }
    missing = [name for name, paths in quality.items() if not paths]
    feature_paths = storage.list_paths(features_container, prefix="macro_daily/version=v")
    if missing or not feature_paths:
        raise RuntimeError(
            f"ECOS audit failed missing_quality={missing} macro_daily={bool(feature_paths)}"
        )
    return {
        "quality_manifests": {name: len(paths) for name, paths in quality.items()},
        "macro_daily_objects": len(feature_paths),
    }


def main() -> None:
    """환경 설정을 읽고 선택한 ECOS pipeline stage를 순서대로 실행한다."""

    load_dotenv()
    args = parse_args()
    series_names = args.series or list(ECOS_SERIES)
    storage = BlobStorage.from_env()
    raw_container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    processed_container = os.getenv("AZURE_STORAGE_CONTAINER_PROCESSED", "processed")
    features_container = os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features")

    if args.stage in {"raw", "all"} or args.validate_metadata:
        client = EcosClient(
            os.getenv("ECOS_API_KEY", ""),
            timeout_seconds=float(os.getenv("ECOS_TIMEOUT_SECONDS", "10")),
        )
        if args.validate_metadata:
            validate_registry(client)
        if args.stage in {"raw", "all"}:
            result = collect_raw(
                storage, client, container=raw_container, series_names=series_names,
                start_date=args.start_date, end_date=args.end_date, incremental=args.incremental,
            )
            print("ECOS RAW COMPLETE " + json.dumps(result, ensure_ascii=False))

    if args.stage in {"processed", "all"}:
        result = [
            build_ecos_processed(
                storage, raw_container=raw_container, processed_container=processed_container,
                series_name=name, schema_version=args.schema_version, overwrite=args.overwrite,
            )
            for name in series_names
        ]
        print("ECOS PROCESSED COMPLETE " + json.dumps(result, ensure_ascii=False))

    if args.stage in {"features", "all"}:
        if set(series_names) != set(ECOS_SERIES):
            raise ValueError("features stage requires all ECOS series")
        result = build_macro_features(
            storage, processed_container=processed_container,
            features_container=features_container, schema_version=args.schema_version,
            feature_version=args.feature_version, overwrite=args.overwrite,
        )
        print("ECOS FEATURES COMPLETE " + json.dumps(result, ensure_ascii=False))

    if args.stage in {"audit", "all"}:
        result = audit_outputs(
            storage, processed_container=processed_container,
            features_container=features_container, series_names=series_names,
        )
        print("ECOS AUDIT OK " + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
