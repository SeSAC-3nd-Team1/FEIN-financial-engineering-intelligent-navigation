"""KRX canonical Raw를 8년 학습용 Processed/Features로 변환한다."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
import gzip
import hashlib
import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import pandas as pd

from collectors.krx_config import OPERATIONS, KrxOperation
from db.connection.session import PROJECT_ROOT
from features.model_dataset import (
    assign_purged_time_split,
    compute_market_features,
    compute_stock_features,
)
from processing.krx import market_index_rows, stock_price_rows
from storage import BlobStorage


DEFAULT_START_DATE = date(2018, 1, 1)
KRX_RAW_RE = re.compile(
    r"^krx/(?P<dataset>[^/]+)/operation=(?P<operation>[^/]+)/"
    r"year=(?P<year>\d{4})/month=(?P<month>\d{2})/(?P<hash>[0-9a-f]{64})\.jsonl\.gz$"
)
STAGES = ("processed", "features", "audit", "all")
OPERATION_BY_NAME = {operation.name.lower(): operation for operation in OPERATIONS}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build KRX 8-year Processed/Features")
    parser.add_argument("--stage", choices=STAGES, default="all")
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--schema-version", default="2")
    parser.add_argument("--feature-version", default="2")
    return parser


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(paths: list[str]) -> str:
    """content-addressed Raw 경로 목록으로 월 단위 변경 여부를 안정적으로 계산한다."""

    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _group_raw_paths(
    storage: BlobStorage,
    container: str,
    *,
    start_date: date,
    end_date: date,
) -> dict[tuple[str, int, int], list[str]]:
    """KRX 가격·지수 Raw만 대상 기간의 월별 dataset으로 그룹화한다."""

    grouped: dict[tuple[str, int, int], list[str]] = defaultdict(list)
    for dataset in ("stock_price", "market_index"):
        for path in storage.list_paths(container, prefix=f"krx/{dataset}/operation="):
            match = KRX_RAW_RE.fullmatch(path)
            if not match:
                continue
            year = int(match.group("year"))
            month = int(match.group("month"))
            month_start = date(year, month, 1)
            if month_start > end_date or (year, month) < (start_date.year, start_date.month):
                continue
            grouped[(dataset, year, month)].append(path)
    return dict(grouped)


def _read_envelopes(storage: BlobStorage, container: str, path: str) -> list[dict[str, Any]]:
    """한 KRX JSONL.gz object를 검증하며 envelope 목록으로 읽는다."""

    result: list[dict[str, Any]] = []
    raw = gzip.decompress(storage.download_bytes(container, path))
    for line_no, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or not isinstance(value.get("payload"), dict):
            raise RuntimeError(f"invalid KRX Raw envelope: {path}:{line_no}")
        result.append(value)
    return result


def _operation_for_path(path: str) -> KrxOperation:
    match = KRX_RAW_RE.fullmatch(path)
    if not match:
        raise RuntimeError(f"invalid KRX Raw path: {path}")
    name = match.group("operation").lower()
    try:
        return OPERATION_BY_NAME[name]
    except KeyError as exc:
        raise RuntimeError(f"unsupported KRX operation in Raw: {name}") from exc


def _as_of(items: list[dict[str, Any]], year: int, month: int) -> date:
    """일별 Raw의 BAS_DD를 service mapper의 as_of로 재사용한다."""

    for item in items:
        text = str(item.get("BAS_DD") or "").strip()
        if len(text) == 8 and text.isdigit():
            return date.fromisoformat(f"{text[:4]}-{text[4:6]}-{text[6:]}")
    return date(year, month, 1)


def _canonical_month(
    storage: BlobStorage,
    container: str,
    *,
    dataset: str,
    year: int,
    month: int,
    paths: list[str],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """한 달의 KRX Raw를 canonical row로 바꾸고 수정 응답은 최신 수집본을 우선한다."""

    rows: list[dict[str, Any]] = []
    for path in sorted(paths):
        envelopes = _read_envelopes(storage, container, path)
        if not envelopes:
            continue
        operation = _operation_for_path(path)
        items = [dict(envelope["payload"]) for envelope in envelopes]
        collected_at = max(str(envelope.get("collectedAt") or "") for envelope in envelopes)
        as_of = _as_of(items, year, month)
        if dataset == "stock_price":
            mapped = stock_price_rows(items, market=operation.market, as_of=as_of)
        else:
            mapped = market_index_rows(items, market=operation.market, as_of=as_of)
        for row in mapped:
            row["_collected_at"] = collected_at
            row["_source_blob"] = path
        rows.extend(mapped)

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise")
    frame = frame.loc[
        (frame["trade_date"].dt.date >= start_date)
        & (frame["trade_date"].dt.date <= end_date)
    ].copy()
    if frame.empty:
        return frame

    if dataset == "stock_price":
        key = ["stock_code", "trade_date"]
    else:
        key = ["index_code", "trade_date"]
    frame = (
        frame.sort_values(key + ["_collected_at"])
        .drop_duplicates(key, keep="last")
        .sort_values(key)
        .reset_index(drop=True)
    )
    if dataset == "market_index":
        frame = frame.rename(
            columns={
                "open_value": "open_index",
                "high_value": "high_index",
                "low_value": "low_index",
                "close_value": "close_index",
            }
        )
    return frame


def _processed_path(dataset: str, year: int, month: int, version: str) -> str:
    name = "krx_stock_price_daily" if dataset == "stock_price" else "krx_market_index_daily"
    return (
        f"{name}/operation=daily/schema=v{version}/"
        f"year={year:04d}/month={month:02d}/part-00000.parquet"
    )


def _quality_path(dataset: str, year: int, month: int, version: str) -> str:
    name = "krx_stock_price_daily" if dataset == "stock_price" else "krx_market_index_daily"
    return (
        f"_quality/{name}/operation=daily/schema=v{version}/"
        f"year={year:04d}/month={month:02d}/manifest.json"
    )


def build_processed(
    storage: BlobStorage,
    *,
    raw_container: str,
    processed_container: str,
    start_date: date,
    end_date: date,
    schema_version: str,
) -> dict[str, Any]:
    """Raw 월 fingerprint가 바뀐 달만 KRX Processed Parquet을 다시 생성한다."""

    grouped = _group_raw_paths(
        storage,
        raw_container,
        start_date=start_date,
        end_date=end_date,
    )
    if not grouped:
        raise RuntimeError("KRX Raw not found for requested period")

    outputs: list[dict[str, Any]] = []
    for (dataset, year, month), paths in sorted(grouped.items()):
        source_fingerprint = _fingerprint(paths)
        output_path = _processed_path(dataset, year, month, schema_version)
        manifest_path = _quality_path(dataset, year, month, schema_version)
        if storage.exists(processed_container, output_path) and storage.exists(
            processed_container, manifest_path
        ):
            manifest = json.loads(storage.download_bytes(processed_container, manifest_path))
            if manifest.get("source_fingerprint") == source_fingerprint:
                print(f"KRX PROCESSED SKIP dataset={dataset} year={year} month={month:02d}")
                outputs.append(manifest)
                continue

        frame = _canonical_month(
            storage,
            raw_container,
            dataset=dataset,
            year=year,
            month=month,
            paths=paths,
            start_date=start_date,
            end_date=end_date,
        )
        if frame.empty:
            continue
        with tempfile.TemporaryDirectory(prefix="fein-krx-processed-") as directory:
            local = Path(directory) / "part-00000.parquet"
            frame.to_parquet(local, index=False, compression="zstd")
            blob = storage.upload_file(
                processed_container,
                output_path,
                local,
                overwrite=True,
                content_type="application/vnd.apache.parquet",
                metadata={
                    "source": "krx",
                    "schema_version": schema_version,
                    "record_count": str(len(frame)),
                    "source_fingerprint": source_fingerprint,
                },
            )
        manifest = {
            "dataset": dataset,
            "year": year,
            "month": month,
            "rows": len(frame),
            "min_date": frame["trade_date"].min().date().isoformat(),
            "max_date": frame["trade_date"].max().date().isoformat(),
            "source_blobs": len(paths),
            "source_fingerprint": source_fingerprint,
            "output_path": output_path,
            "bytes": blob.size,
        }
        storage.upload_bytes(
            processed_container,
            manifest_path,
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            overwrite=True,
            content_type="application/json",
        )
        outputs.append(manifest)
        print(
            f"KRX PROCESSED WRITE dataset={dataset} year={year} month={month:02d} "
            f"rows={len(frame)}"
        )

    overall_fingerprint = _fingerprint(
        [f"{item['dataset']}:{item['year']}:{item['month']}:{item['source_fingerprint']}" for item in outputs]
    )
    payload = {
        "generated_at": _utc_now(),
        "schema_version": schema_version,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "source_fingerprint": overall_fingerprint,
        "partitions": outputs,
    }
    storage.upload_bytes(
        processed_container,
        f"_manifests/krx-history/schema=v{schema_version}/manifest.json",
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        overwrite=True,
        content_type="application/json",
    )
    return payload


def _load_processed(
    storage: BlobStorage,
    container: str,
    dataset_name: str,
    schema_version: str,
) -> pd.DataFrame:
    prefix = f"{dataset_name}/operation=daily/schema=v{schema_version}/"
    frames = [
        pd.read_parquet(io.BytesIO(storage.download_bytes(container, path)))
        for path in storage.list_paths(container, prefix=prefix)
        if path.endswith(".parquet")
    ]
    if not frames:
        raise RuntimeError(f"KRX processed dataset not found: {dataset_name}")
    return pd.concat(frames, ignore_index=True)


def _write_feature_monthly(
    storage: BlobStorage,
    container: str,
    *,
    dataset: str,
    frame: pd.DataFrame,
    date_column: str,
    version: str,
) -> list[dict[str, Any]]:
    """Feature를 월별 Parquet으로 덮어써 전체 rolling 계산과 경계를 일치시킨다."""

    data = frame.copy()
    data[date_column] = pd.to_datetime(data[date_column], errors="raise")
    data["_year"] = data[date_column].dt.year
    data["_month"] = data[date_column].dt.month
    outputs: list[dict[str, Any]] = []
    for (year, month), monthly in data.groupby(["_year", "_month"], sort=True):
        output = monthly.drop(columns=["_year", "_month"]).reset_index(drop=True)
        path = (
            f"{dataset}/version=v{version}/year={int(year):04d}/"
            f"month={int(month):02d}/part-00000.parquet"
        )
        with tempfile.TemporaryDirectory(prefix="fein-krx-feature-") as directory:
            local = Path(directory) / "part-00000.parquet"
            output.to_parquet(local, index=False, compression="zstd")
            blob = storage.upload_file(
                container,
                path,
                local,
                overwrite=True,
                content_type="application/vnd.apache.parquet",
                metadata={
                    "source": "krx",
                    "feature_version": version,
                    "record_count": str(len(output)),
                },
            )
        outputs.append({"path": path, "rows": len(output), "bytes": blob.size})
    return outputs


def build_features(
    storage: BlobStorage,
    *,
    processed_container: str,
    features_container: str,
    schema_version: str,
    feature_version: str,
) -> dict[str, Any]:
    """KRX 가격·지수를 기존 Feature 함수에 연결해 v2 학습 Dataset을 만든다."""

    processed_manifest_path = (
        f"_manifests/krx-history/schema=v{schema_version}/manifest.json"
    )
    if not storage.exists(processed_container, processed_manifest_path):
        raise RuntimeError("KRX processed manifest not found")
    processed_manifest = json.loads(
        storage.download_bytes(processed_container, processed_manifest_path)
    )
    source_fingerprint = str(processed_manifest["source_fingerprint"])
    feature_manifest_path = (
        f"_manifests/krx-history-features/version=v{feature_version}/manifest.json"
    )
    if storage.exists(features_container, feature_manifest_path):
        previous = json.loads(storage.download_bytes(features_container, feature_manifest_path))
        if previous.get("source_fingerprint") == source_fingerprint:
            print("KRX FEATURES SKIP source fingerprint unchanged")
            return previous

    stock_source = _load_processed(
        storage,
        processed_container,
        "krx_stock_price_daily",
        schema_version,
    )
    market_source = _load_processed(
        storage,
        processed_container,
        "krx_market_index_daily",
        schema_version,
    )
    stock, split = assign_purged_time_split(compute_stock_features(stock_source))
    market = compute_market_features(market_source)

    stock_outputs = _write_feature_monthly(
        storage,
        features_container,
        dataset="model_stock_daily",
        frame=stock,
        date_column="trade_date",
        version=feature_version,
    )
    market_outputs = _write_feature_monthly(
        storage,
        features_container,
        dataset="market_index_daily",
        frame=market,
        date_column="trade_date",
        version=feature_version,
    )
    payload = {
        "generated_at": _utc_now(),
        "feature_version": feature_version,
        "processed_schema_version": schema_version,
        "source": "KRX",
        "source_fingerprint": source_fingerprint,
        "model_stock_daily": {
            "status": "training_ready",
            "rows": len(stock),
            "files": stock_outputs,
            "split": split,
        },
        "market_index_daily": {
            "status": "training_ready",
            "rows": len(market),
            "files": market_outputs,
        },
        "min_trade_date": min(stock["trade_date"].min(), market["trade_date"].min()).date().isoformat(),
        "max_trade_date": max(stock["trade_date"].max(), market["trade_date"].max()).date().isoformat(),
    }
    storage.upload_bytes(
        features_container,
        feature_manifest_path,
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        overwrite=True,
        content_type="application/json",
    )
    print(
        "KRX FEATURES COMPLETE "
        f"stock_rows={len(stock)} market_rows={len(market)} "
        f"range={payload['min_trade_date']}..{payload['max_trade_date']}"
    )
    return payload


def audit(
    storage: BlobStorage,
    *,
    features_container: str,
    feature_version: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """Feature manifest의 기간 경계가 요청한 2018년 이후 범위를 실제로 덮는지 확인한다."""

    path = f"_manifests/krx-history-features/version=v{feature_version}/manifest.json"
    if not storage.exists(features_container, path):
        raise RuntimeError("KRX feature manifest not found")
    manifest = json.loads(storage.download_bytes(features_container, path))
    first = date.fromisoformat(manifest["min_trade_date"])
    last = date.fromisoformat(manifest["max_trade_date"])
    # 휴장일 경계는 허용하되 월 단위 누락을 성공으로 보지 않도록 7일만 허용한다.
    if (first - start_date).days > 7 or (end_date - last).days > 7:
        raise RuntimeError(
            "KRX feature coverage incomplete: "
            f"requested={start_date}..{end_date} actual={first}..{last}"
        )
    result = {
        "status": "ok",
        "requested_start": start_date.isoformat(),
        "requested_end": end_date.isoformat(),
        "actual_start": first.isoformat(),
        "actual_end": last.isoformat(),
    }
    print("KRX HISTORY AUDIT OK " + json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    """선택한 KRX 파생 단계와 coverage audit을 순서대로 실행한다."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    args = _parser().parse_args()
    if args.start_date > args.end_date:
        raise SystemExit("--start-date must not be after --end-date")

    storage = BlobStorage.from_env()
    raw_container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    processed_container = os.getenv("AZURE_STORAGE_CONTAINER_PROCESSED", "processed")
    features_container = os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features")

    if args.stage in {"processed", "all"}:
        build_processed(
            storage,
            raw_container=raw_container,
            processed_container=processed_container,
            start_date=args.start_date,
            end_date=args.end_date,
            schema_version=args.schema_version,
        )
    if args.stage in {"features", "all"}:
        build_features(
            storage,
            processed_container=processed_container,
            features_container=features_container,
            schema_version=args.schema_version,
            feature_version=args.feature_version,
        )
    if args.stage in {"audit", "all"}:
        audit(
            storage,
            features_container=features_container,
            feature_version=args.feature_version,
            start_date=args.start_date,
            end_date=args.end_date,
        )


if __name__ == "__main__":
    main()
