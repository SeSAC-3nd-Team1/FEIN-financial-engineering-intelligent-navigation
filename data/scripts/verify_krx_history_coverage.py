"""KRX v2 Processed/Features의 월별·거래일 연속성을 독립적으로 검증한다."""

from __future__ import annotations

import argparse
from datetime import date
import io
import json
import os
from typing import Any

from dotenv import load_dotenv
import pandas as pd

from db.connection.session import PROJECT_ROOT
from processing.coverage import coverage_is_complete, summarize_trading_dates
from storage import BlobStorage


DATASET_CONFIG = {
    "stock_price": "model_stock_daily",
    "market_index": "market_index_daily",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify strict KRX history coverage")
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--schema-version", default="2")
    parser.add_argument("--feature-version", default="2")
    return parser


def _expected_months(start_date: date, end_date: date) -> set[tuple[int, int]]:
    """요청 범위가 걸치는 모든 달을 (연, 월) 집합으로 만든다."""

    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    result: set[tuple[int, int]] = set()
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        result.add((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return result


def _manifest_months(
    manifest: dict[str, Any],
    *,
    dataset: str,
) -> set[tuple[int, int]]:
    """최신 Processed manifest에서 dataset별 실제 생성 월만 추출한다."""

    return {
        (int(item["year"]), int(item["month"]))
        for item in manifest.get("partitions", [])
        if item.get("dataset") == dataset and int(item.get("rows", 0)) > 0
    }


def _feature_trade_dates(
    storage: BlobStorage,
    container: str,
    *,
    dataset: str,
    feature_version: str,
    start_date: date,
    end_date: date,
) -> tuple[date, ...]:
    """월별 Feature에서 trade_date 한 컬럼만 읽어 고유 거래일을 만든다."""

    prefix = f"{dataset}/version=v{feature_version}/"
    values: set[date] = set()
    for path in storage.list_paths(container, prefix=prefix):
        if not path.endswith(".parquet"):
            continue
        frame = pd.read_parquet(
            io.BytesIO(storage.download_bytes(container, path)),
            columns=["trade_date"],
        )
        dates = pd.to_datetime(frame["trade_date"], errors="coerce").dropna().dt.date
        values.update(value for value in dates if start_date <= value <= end_date)
    return tuple(sorted(values))


def verify(
    storage: BlobStorage,
    *,
    processed_container: str,
    features_container: str,
    start_date: date,
    end_date: date,
    schema_version: str,
    feature_version: str,
) -> dict[str, Any]:
    """stock/index 각각에 대해 월 partition, 거래일 밀도, 내부 최대 공백을 모두 검증한다."""

    manifest_path = f"_manifests/krx-history/schema=v{schema_version}/manifest.json"
    if not storage.exists(processed_container, manifest_path):
        raise RuntimeError("KRX processed history manifest not found")
    manifest = json.loads(storage.download_bytes(processed_container, manifest_path))
    expected_months = _expected_months(start_date, end_date)
    result: dict[str, Any] = {}
    failures: list[str] = []

    for source_dataset, feature_dataset in DATASET_CONFIG.items():
        actual_months = _manifest_months(manifest, dataset=source_dataset)
        missing_months = sorted(expected_months - actual_months)
        trade_dates = _feature_trade_dates(
            storage,
            features_container,
            dataset=feature_dataset,
            feature_version=feature_version,
            start_date=start_date,
            end_date=end_date,
        )
        coverage = summarize_trading_dates(
            trade_dates,
            start_date=start_date,
            end_date=end_date,
        )
        complete = coverage_is_complete(
            coverage,
            start_date=start_date,
            end_date=end_date,
        )
        result[source_dataset] = {
            "first_date": coverage.first_date.isoformat() if coverage.first_date else None,
            "last_date": coverage.last_date.isoformat() if coverage.last_date else None,
            "trading_days": coverage.trading_days,
            "weekday_days": coverage.weekday_days,
            "weekday_density": round(coverage.weekday_density, 6),
            "max_gap_days": coverage.max_gap_days,
            "missing_months": [f"{year:04d}-{month:02d}" for year, month in missing_months],
        }
        if missing_months:
            failures.append(f"{source_dataset}:missing_months={len(missing_months)}")
        if not complete:
            failures.append(
                f"{source_dataset}:density={coverage.weekday_density:.3f}:gap={coverage.max_gap_days}"
            )

    if failures:
        raise RuntimeError("KRX strict coverage failed: " + ", ".join(failures))

    payload = {
        "status": "ok",
        "requested_start": start_date.isoformat(),
        "requested_end": end_date.isoformat(),
        "datasets": result,
    }
    print("KRX STRICT COVERAGE OK " + json.dumps(payload, ensure_ascii=False))
    return payload


def main(argv: list[str] | None = None) -> int:
    """Azure v2 산출물의 KRX 장기 coverage를 검증한다."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    args = _parser().parse_args(argv)
    if args.start_date > args.end_date:
        raise SystemExit("--start-date must not be after --end-date")
    storage = BlobStorage.from_env()
    verify(
        storage,
        processed_container=os.getenv("AZURE_STORAGE_CONTAINER_PROCESSED", "processed"),
        features_container=os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features"),
        start_date=args.start_date,
        end_date=args.end_date,
        schema_version=args.schema_version,
        feature_version=args.feature_version,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
