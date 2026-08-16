"""Processed Parquet에서 월별 주가 Feature를 계산해 versioned Blob으로 저장한다."""

from __future__ import annotations

import argparse
import io
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from storage import BlobStorage, build_feature_path


PROCESSED_RE = re.compile(
    r"^stock_price/schema=v(?P<version>[^/]+)/year=(?P<year>\d{4})/"
    r"month=(?P<month>\d{2})/part-00000\.parquet$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--processed-schema-version", default="1")
    parser.add_argument("--feature-version", default="1")
    parser.add_argument("--warmup-days", type=int, default=60)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _safe_version(value: str) -> str:
    """Blob 경로에 안전한 schema/feature version 형식만 허용한다."""

    cleaned = value.strip()
    if not cleaned or any(ch not in "0123456789._-" for ch in cleaned):
        raise ValueError("version contains unsafe characters")
    return cleaned


def feature_path(*, month: date, version: str) -> str:
    """주가 Feature의 version + 월 partition 경로를 생성한다."""

    return build_feature_path(
        "stock_price",
        partition_date=month,
        version=_safe_version(version),
    )


def compute_price_features(frame: pd.DataFrame) -> pd.DataFrame:
    """종목별 과거 시계열만 사용해 기본 가격/거래량 Feature를 계산한다.

    모든 rolling/shift 연산은 ``stock_code``별 group 안에서 수행한다. 다른 종목의 값이
    window에 섞이면 학습 데이터가 오염되므로 정렬 후 종목 경계를 명시적으로 유지한다.
    """

    required = {"stock_code", "trade_date", "close_price", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"processed stock_price missing columns: {sorted(missing)}")
    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="raise")
    data["close_price"] = pd.to_numeric(data["close_price"], errors="coerce")
    data["volume"] = pd.to_numeric(data["volume"], errors="coerce")
    data = data.sort_values(["stock_code", "trade_date"]).reset_index(drop=True)

    # 미래값을 사용하지 않도록 현재 행 이전까지의 시계열을 shift/rolling으로만 참조한다.
    close = data.groupby("stock_code", sort=False)["close_price"]
    data["return_1d"] = close.pct_change(fill_method=None)
    previous_close = close.shift(1)
    data["log_return_1d"] = np.log(data["close_price"] / previous_close)
    data["sma_5"] = close.transform(lambda series: series.rolling(5, min_periods=5).mean())
    data["sma_20"] = close.transform(lambda series: series.rolling(20, min_periods=20).mean())
    data["momentum_20"] = data["close_price"] / close.shift(20) - 1
    data["volatility_20"] = data.groupby("stock_code", sort=False)["return_1d"].transform(
        lambda series: series.rolling(20, min_periods=20).std()
    )
    data["volume_sma_20"] = data.groupby("stock_code", sort=False)["volume"].transform(
        lambda series: series.rolling(20, min_periods=20).mean()
    )
    return data


def _month_key(value: date) -> tuple[int, int]:
    """월 단위 비교를 위한 (year, month) key를 만든다."""

    return value.year, value.month


def load_processed(
    storage: BlobStorage,
    *,
    container: str,
    schema_version: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """요청 기간과 겹치는 Processed stock_price 월 partition만 읽는다."""

    schema_version = _safe_version(schema_version)
    client = storage.service_client.get_container_client(container)
    frames: list[pd.DataFrame] = []
    start_key = _month_key(start)
    end_key = _month_key(end)
    prefix = f"stock_price/schema=v{schema_version}/"
    for blob in client.list_blobs(name_starts_with=prefix):
        match = PROCESSED_RE.match(str(blob.name))
        if match is None or match.group("version") != schema_version:
            continue
        key = (int(match.group("year")), int(match.group("month")))
        if start_key <= key <= end_key:
            frames.append(pd.read_parquet(io.BytesIO(storage.download_bytes(container, str(blob.name)))))
    if not frames:
        raise RuntimeError(
            f"No processed stock_price Parquet found for {start}..{end} schema=v{schema_version}"
        )
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    args = parse_args()
    if args.env_file:
        if not args.env_file.is_file():
            raise FileNotFoundError(f"env file not found: {args.env_file}")
        load_dotenv(args.env_file, override=False)
    if args.start > args.end:
        raise ValueError("--start must be on or before --end")
    if args.warmup_days < 0:
        raise ValueError("--warmup-days must not be negative")

    storage = BlobStorage.from_env()
    processed_container = os.getenv("AZURE_STORAGE_CONTAINER_PROCESSED", "processed")
    features_container = os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features")

    # 20일 rolling/momentum 값을 요청 시작일부터 계산하려면 시작일 이전 관측치가 필요하다.
    # warm-up 구간은 계산에만 사용하고 최종 Feature 출력에서는 다시 제거한다.
    source = load_processed(
        storage,
        container=processed_container,
        schema_version=args.processed_schema_version,
        start=args.start - timedelta(days=args.warmup_days),
        end=args.end,
    )
    features = compute_price_features(source)
    mask = (features["trade_date"].dt.date >= args.start) & (features["trade_date"].dt.date <= args.end)
    features = features.loc[mask].copy()
    if features.empty:
        raise RuntimeError("Feature output is empty for requested range")

    generated_at = datetime.now(timezone.utc).isoformat()
    features["year"] = features["trade_date"].dt.year
    features["month"] = features["trade_date"].dt.month
    files = 0
    rows = 0
    for (year, month), monthly in features.groupby(["year", "month"], sort=True):
        output = monthly.drop(columns=["year", "month"]).reset_index(drop=True)
        partition_date = date(int(year), int(month), 1)
        # Parquet 생성용 임시 파일은 업로드가 끝나는 즉시 제거해 로컬을 영구 저장소로 쓰지 않는다.
        with tempfile.TemporaryDirectory(prefix="fein-features-") as directory:
            local = Path(directory) / "part-00000.parquet"
            output.to_parquet(local, index=False, compression="zstd")
            path = feature_path(month=partition_date, version=args.feature_version)
            result = storage.upload_file(
                features_container,
                path,
                local,
                metadata={
                    "dataset": "stock_price",
                    "layer": "features",
                    "feature_version": args.feature_version,
                    "processed_schema_version": args.processed_schema_version,
                    "source_range": f"{args.start}/{args.end}",
                    "record_count": str(len(output)),
                    "generated_at": generated_at,
                    "git_sha": os.getenv("GIT_SHA", "unknown"),
                    "features": "return_1d,log_return_1d,sma_5,sma_20,momentum_20,volatility_20,volume_sma_20",
                },
                content_type="application/vnd.apache.parquet",
                overwrite=args.overwrite,
            )
            files += 1
            rows += len(output)
            print(f"FEATURE WRITE rows={len(output)} bytes={result.size} path={result.path}")
    print(f"FEATURE BUILD COMPLETE files={files} rows={rows} version=v{args.feature_version}")


if __name__ == "__main__":
    main()
