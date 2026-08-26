"""Algorithm ver.0/ver.1/ver.1.1용 OHLCV Dataset을 생성한다."""

from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from storage import BlobStorage

SOURCE_PREFIX = "model_stock_daily/version=v2/"
SOURCE_COLUMNS = [
    "stock_code",
    "trade_date",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "volume",
]
OUTPUT_COLUMNS = ["symbol", "Date", "Open", "High", "Low", "Close", "Volume"]


def _period(path: str) -> tuple[int, int]:
    """월별 Feature Blob 경로에서 파티션 연월을 읽는다."""

    parts = Path(path).parts
    return int(parts[-3].split("=", 1)[1]), int(parts[-2].split("=", 1)[1])


def _paths(storage: BlobStorage, container: str) -> list[str]:
    """Algorithm 원천 Feature의 월별 Parquet 경로를 정렬해 반환한다."""

    paths = [
        path
        for path in storage.list_paths(container, prefix=SOURCE_PREFIX)
        if path.endswith(".parquet")
    ]
    if not paths:
        raise RuntimeError(f"source dataset not found: {SOURCE_PREFIX}")
    return sorted(paths)


def _transform(frame: pd.DataFrame, symbol: str | None) -> tuple[pd.DataFrame, int]:
    """KRX Feature를 Algorithm OHLCV 계약으로 변환하고 검증 탈락 건수를 반환한다."""

    missing = set(SOURCE_COLUMNS) - set(frame.columns)
    if missing:
        raise RuntimeError(f"source columns missing: {sorted(missing)}")
    data = frame[SOURCE_COLUMNS].copy()
    data["stock_code"] = data["stock_code"].astype("string")
    if symbol:
        data = data.loc[data["stock_code"] == symbol].copy()
    data = data.rename(
        columns={
            "stock_code": "symbol",
            "trade_date": "Date",
            "open_price": "Open",
            "high_price": "High",
            "low_price": "Low",
            "close_price": "Close",
            "volume": "Volume",
        }
    )
    data["Date"] = pd.to_datetime(data["Date"], errors="raise")
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        data[column] = pd.to_numeric(data[column], errors="raise")
    data = data.sort_values(["symbol", "Date"]).drop_duplicates(["symbol", "Date"])
    values = ["Open", "High", "Low", "Close", "Volume"]
    invalid = data[values].isna().any(axis=1)
    invalid |= (data[["Open", "High", "Low", "Close"]] <= 0).any(axis=1)
    invalid |= data["Volume"] < 0
    rejected = int(invalid.sum())
    data = data.loc[~invalid].copy()
    return data[OUTPUT_COLUMNS].reset_index(drop=True), rejected


def build(
    storage: BlobStorage,
    *,
    container: str,
    output_version: str,
    symbol: str | None,
    overwrite: bool,
) -> dict:
    """원천 월별 Feature를 Algorithm 전달용 Dataset으로 저장한다.

    가격·거래량 이상 행을 임의 보간하지 않고 제외해 Algorithm에 조용한 가짜 값을
    전달하지 않는다. 월별 경로와 manifest를 함께 기록해 후속 전달자가 동일한 버전을
    재현할 수 있게 한다.
    """

    source_paths = _paths(storage, container)
    outputs: list[dict] = []
    symbols: set[str] = set()
    total_rows = 0
    rejected_rows = 0
    min_date = None
    max_date = None

    for source_path in source_paths:
        frame = pd.read_parquet(
            io.BytesIO(storage.download_bytes(container, source_path)),
            columns=SOURCE_COLUMNS,
        )
        output, rejected = _transform(frame, symbol)
        rejected_rows += rejected
        if output.empty:
            continue
        symbols.update(output["symbol"].dropna().astype(str).unique())
        total_rows += len(output)
        month_min = output["Date"].min()
        month_max = output["Date"].max()
        min_date = month_min if min_date is None else min(min_date, month_min)
        max_date = month_max if max_date is None else max(max_date, month_max)
        year, month = _period(source_path)
        path = f"algorithm_ohlcv/version=v{output_version}/year={year:04d}/month={month:02d}/part-00000.parquet"
        with tempfile.TemporaryDirectory(prefix="algorithm-ohlcv-") as directory:
            local = Path(directory) / "part-00000.parquet"
            output.to_parquet(local, index=False, compression="zstd")
            blob = storage.upload_file(
                container,
                path,
                local,
                overwrite=overwrite,
                content_type="application/vnd.apache.parquet",
                metadata={
                    "dataset": "algorithm_ohlcv",
                    "version": output_version,
                    "record_count": str(len(output)),
                    "source": "KRX",
                },
            )
        outputs.append({"path": path, "rows": len(output), "bytes": blob.size})
        print(f"ALGORITHM DATASET WRITE rows={len(output)} path={path}")

    manifest = {
        "dataset": "algorithm_ohlcv",
        "version": output_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset": "model_stock_daily/version=v2/",
        "source": "KRX",
        "rows": total_rows,
        "rejected_rows": rejected_rows,
        "symbols": len(symbols),
        "symbol_filter": symbol,
        "min_date": min_date.date().isoformat() if min_date is not None else None,
        "max_date": max_date.date().isoformat() if max_date is not None else None,
        "columns": OUTPUT_COLUMNS,
        "algorithm_input_columns": ["Date", "Open", "High", "Low", "Close", "Volume"],
        "extra_column": "symbol",
        "files": outputs,
        "target_columns_included": False,
        "corporate_action_adjusted_price": False,
    }
    manifest_path = (
        f"_manifests/algorithm_ohlcv/version=v{output_version}/manifest.json"
    )
    storage.upload_bytes(
        container,
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        content_type="application/json",
        overwrite=True,
    )
    return manifest


def main() -> None:
    """환경변수와 CLI 옵션으로 Algorithm Dataset 생성을 실행한다."""

    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    parser = argparse.ArgumentParser(
        description="Build Algorithm OHLCV dataset from KRX features"
    )
    parser.add_argument("--version", default="1")
    parser.add_argument("--symbol", help="Export one stock code only, e.g. 005930")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    storage = BlobStorage.from_env()
    manifest = build(
        storage,
        container=os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features"),
        output_version=args.version,
        symbol=args.symbol,
        overwrite=args.overwrite,
    )
    print(
        f"ALGORITHM DATASET COMPLETE rows={manifest['rows']} "
        f"symbols={manifest['symbols']} rejected={manifest['rejected_rows']} "
        f"range={manifest['min_date']}..{manifest['max_date']}"
    )


if __name__ == "__main__":
    main()
