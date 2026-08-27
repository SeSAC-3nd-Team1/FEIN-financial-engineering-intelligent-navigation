"""Algorithm ver.0/ver.1/ver.1.1용 OHLCV Dataset을 생성한다."""

from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
from collections import Counter
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
ALGORITHM_INPUT_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]
OUTPUT_COLUMNS = [
    "symbol",
    *ALGORITHM_INPUT_COLUMNS,
    "is_tradable",
    "data_status",
    "quality_reason",
]


def _period(path: str) -> tuple[int, int]:
    """월별 Feature Blob 경로에서 파티션 연월을 읽는다."""

    parts = Path(path).parts
    return int(parts[-3].split("=", 1)[1]), int(parts[-2].split("=", 1)[1])


def _paths(storage: BlobStorage, container: str) -> list[str]:
    """Algorithm 직접 입력 Feature의 월별 Parquet 경로를 정렬해 반환한다."""

    paths = [
        path
        for path in storage.list_paths(container, prefix=SOURCE_PREFIX)
        if path.endswith(".parquet")
    ]
    if not paths:
        raise RuntimeError(f"source dataset not found: {SOURCE_PREFIX}")
    return sorted(paths)


def _quality_masks(data: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """입력 Feature 값을 수정하지 않고 보수적 주문 허용 판정 mask를 만든다.

    이 mask는 가격 패턴 기반 품질 규칙이며 KRX 공식 거래정지·시장조치 상태가 아니다.
    """

    intraday = data[["Open", "High", "Low"]]
    prices = data[["Open", "High", "Low", "Close"]]
    positive_prices = prices.notna().all(axis=1) & (prices > 0).all(axis=1)
    no_intraday_price = intraday.notna().all(axis=1) & intraday.eq(0).all(axis=1)
    partial_non_positive_ohl = (intraday.notna() & (intraday <= 0)).any(
        axis=1
    ) & ~no_intraday_price
    inconsistent_ohlc = positive_prices & (
        (data["High"] < data["Low"])
        | (data["High"] < data["Open"])
        | (data["High"] < data["Close"])
        | (data["Low"] > data["Open"])
        | (data["Low"] > data["Close"])
    )
    return [
        ("MISSING_IDENTITY", data["symbol"].isna() | data["Date"].isna()),
        ("MISSING_OHLCV", data[ALGORITHM_INPUT_COLUMNS[1:]].isna().any(axis=1)),
        ("NON_POSITIVE_CLOSE", data["Close"].notna() & (data["Close"] <= 0)),
        ("NEGATIVE_VOLUME", data["Volume"].notna() & (data["Volume"] < 0)),
        ("NO_INTRADAY_PRICE", no_intraday_price),
        ("PARTIAL_NON_POSITIVE_OHL", partial_non_positive_ohl),
        ("INCONSISTENT_OHLC", inconsistent_ohlc),
    ]


def _transform(
    frame: pd.DataFrame, symbol: str | None
) -> tuple[pd.DataFrame, dict[str, int]]:
    """KRX Feature를 상태 정보가 포함된 Algorithm OHLCV 계약으로 변환한다.

    거래정지·거래 미발생 가능 행을 삭제하거나 가격 보간하지 않는다. 직접 입력 Feature의
    OHLCV를 유지하고 가격 패턴 기반 신규 주문 허용 여부와 품질 사유를 별도 컬럼으로
    제공한다. 상태 컬럼은 KRX 공식 거래상태가 아니라 Data 계층의 파생값이다.
    """

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
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    duplicate = data.duplicated(["symbol", "Date"], keep=False)
    if duplicate.any():
        raise RuntimeError(f"duplicate symbol and Date rows: {int(duplicate.sum())}")

    quality_reason = pd.Series("", index=data.index, dtype="string")
    reason_counts: Counter[str] = Counter()
    for reason, mask in _quality_masks(data):
        count = int(mask.sum())
        if not count:
            continue
        separator = mask & quality_reason.ne("")
        quality_reason.loc[separator] = quality_reason.loc[separator] + ";"
        quality_reason.loc[mask] = quality_reason.loc[mask] + reason
        reason_counts[reason] = count

    data["quality_reason"] = quality_reason
    data["is_tradable"] = quality_reason.eq("")
    data["data_status"] = data["is_tradable"].map(
        {True: "TRADABLE", False: "NOT_TRADABLE"}
    )
    stats = {
        "rows": len(data),
        "tradable_rows": int(data["is_tradable"].sum()),
        "non_tradable_rows": int((~data["is_tradable"]).sum()),
        **{
            f"reason_{reason}": count for reason, count in sorted(reason_counts.items())
        },
    }
    data = data.sort_values(["symbol", "Date"])
    return data[OUTPUT_COLUMNS].reset_index(drop=True), stats


def build(
    storage: BlobStorage,
    *,
    container: str,
    output_version: str,
    symbol: str | None,
    overwrite: bool,
) -> dict:
    """직접 입력 Feature를 상태 보존형 Algorithm Dataset으로 저장한다.

    품질 이상 가능성이 있는 행도 삭제하지 않고 입력 OHLCV와 파생 상태를 함께 보존한다.
    월별 경로와 manifest에는 KRX 제공값과 Data 파생값의 경계를 기록한다.
    """

    source_paths = _paths(storage, container)
    outputs: list[dict] = []
    symbols: set[str] = set()
    total_rows = 0
    tradable_rows = 0
    non_tradable_rows = 0
    reason_counts: Counter[str] = Counter()
    min_date = None
    max_date = None

    for source_path in source_paths:
        frame = pd.read_parquet(
            io.BytesIO(storage.download_bytes(container, source_path)),
            columns=SOURCE_COLUMNS,
        )
        output, quality = _transform(frame, symbol)
        tradable_rows += quality["tradable_rows"]
        non_tradable_rows += quality["non_tradable_rows"]
        reason_counts.update(
            {
                key.removeprefix("reason_"): value
                for key, value in quality.items()
                if key.startswith("reason_")
            }
        )
        if output.empty:
            continue
        symbols.update(output["symbol"].dropna().astype(str).unique())
        total_rows += len(output)
        observed_dates = output["Date"].dropna()
        if not observed_dates.empty:
            month_min = observed_dates.min()
            month_max = observed_dates.max()
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
        outputs.append(
            {
                "path": path,
                "rows": len(output),
                "tradable_rows": quality["tradable_rows"],
                "non_tradable_rows": quality["non_tradable_rows"],
                "bytes": blob.size,
            }
        )
        print(f"ALGORITHM DATASET WRITE rows={len(output)} path={path}")

    manifest = {
        "dataset": "algorithm_ohlcv",
        "version": output_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset": "model_stock_daily/version=v2/",
        "direct_source_dataset": "features/model_stock_daily/version=v2/",
        "source": "KRX",
        "source_provider": "KRX official API",
        "source_lineage": [
            "KRX API",
            "canonical raw",
            "krx_stock_price_daily processed",
            "model_stock_daily/version=v2 feature",
            "algorithm_ohlcv/version=v2",
        ],
        "ohlcv_value_policy": "preserve_direct_source_values_without_imputation",
        "status_columns_origin": "derived_by_data_quality_rules",
        "tradability_semantics": "algorithm_order_eligibility_heuristic",
        "official_trading_halt_status_included": False,
        "quality_reason_definitions": {
            "NO_INTRADAY_PRICE": (
                "Open, High, and Low are all zero in the direct source; "
                "this is not an official KRX halt reason"
            )
        },
        "rows": total_rows,
        "rejected_rows": 0,
        "tradable_rows": tradable_rows,
        "non_tradable_rows": non_tradable_rows,
        "quality_reason_counts": dict(sorted(reason_counts.items())),
        "row_preservation_policy": "preserve_source_rows_with_status",
        "symbols": len(symbols),
        "symbol_filter": symbol,
        "min_date": min_date.date().isoformat() if min_date is not None else None,
        "max_date": max_date.date().isoformat() if max_date is not None else None,
        "columns": OUTPUT_COLUMNS,
        "algorithm_input_columns": ALGORITHM_INPUT_COLUMNS,
        "status_columns": ["is_tradable", "data_status", "quality_reason"],
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
    parser.add_argument("--version", default="2")
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
        f"symbols={manifest['symbols']} tradable={manifest['tradable_rows']} "
        f"non_tradable={manifest['non_tradable_rows']} "
        f"range={manifest['min_date']}..{manifest['max_date']}"
    )


if __name__ == "__main__":
    main()
