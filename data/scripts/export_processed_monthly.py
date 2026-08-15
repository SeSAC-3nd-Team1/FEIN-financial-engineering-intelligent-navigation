"""Export normalized PostgreSQL market data to monthly Parquet in Azure Blob.

Processed data is derived and rebuildable. Raw Blob remains the source of truth;
PostgreSQL supplies normalized service-ready rows, and this job materializes
columnar monthly files for analytics and downstream feature engineering.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
from sqlalchemy import select

from db.connection import build_engine
from db.models import MarketIndexDaily, StockMaster, StockPriceDaily
from storage import BlobStorage
from transforms import export_query_to_parquet


SUPPORTED_DATASETS = ("stock_price", "market_index")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=SUPPORTED_DATASETS, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--schema-version", default="1")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def month_windows(start: date, end: date) -> list[tuple[date, date]]:
    if start > end:
        raise ValueError("start must be on or before end")
    windows: list[tuple[date, date]] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        window_start = max(start, cursor)
        window_end = min(end, next_month.fromordinal(next_month.toordinal() - 1))
        windows.append((window_start, window_end))
        cursor = next_month
    return windows


def build_processed_path(dataset: str, *, month: date, schema_version: str) -> str:
    version = schema_version.strip()
    if not version or any(ch not in "0123456789._-" for ch in version):
        raise ValueError("schema_version contains unsafe characters")
    return (
        f"{dataset}/schema=v{version}/year={month:%Y}/month={month:%m}/"
        "part-00000.parquet"
    )


def build_query(dataset: str, start: date, end: date):
    if dataset == "stock_price":
        return (
            select(
                StockMaster.stock_code,
                StockPriceDaily.trade_date,
                StockPriceDaily.open_price,
                StockPriceDaily.high_price,
                StockPriceDaily.low_price,
                StockPriceDaily.close_price,
                StockPriceDaily.volume,
                StockPriceDaily.trading_value,
                StockPriceDaily.price_type,
            )
            .join(StockMaster, StockMaster.stock_id == StockPriceDaily.stock_id)
            .where(StockPriceDaily.trade_date.between(start, end))
            .order_by(StockPriceDaily.trade_date, StockMaster.stock_code)
        )
    if dataset == "market_index":
        return (
            select(
                MarketIndexDaily.index_code,
                MarketIndexDaily.trade_date,
                MarketIndexDaily.open_value,
                MarketIndexDaily.high_value,
                MarketIndexDaily.low_value,
                MarketIndexDaily.close_value,
                MarketIndexDaily.change_rate,
            )
            .where(MarketIndexDaily.trade_date.between(start, end))
            .order_by(MarketIndexDaily.trade_date, MarketIndexDaily.index_code)
        )
    raise ValueError(f"unsupported dataset: {dataset}")


def main() -> None:
    args = parse_args()
    engine = build_engine()
    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_PROCESSED", "processed")
    generated_at = datetime.now(timezone.utc).isoformat()
    exported_files = 0
    exported_rows = 0

    for window_start, window_end in month_windows(args.start, args.end):
        query = build_query(args.dataset, window_start, window_end)
        with tempfile.TemporaryDirectory(prefix="fein-processed-") as directory:
            local_path = export_query_to_parquet(
                engine,
                query,
                Path(directory) / "part-00000.parquet",
            )
            parquet = pq.ParquetFile(local_path)
            row_count = parquet.metadata.num_rows
            if row_count == 0:
                print(
                    f"SKIP empty dataset={args.dataset} "
                    f"range={window_start}..{window_end}"
                )
                continue
            blob_path = build_processed_path(
                args.dataset,
                month=window_start,
                schema_version=args.schema_version,
            )
            result = storage.upload_file(
                container,
                blob_path,
                local_path,
                metadata={
                    "dataset": args.dataset,
                    "layer": "processed",
                    "schema_version": args.schema_version,
                    "source": "azure-postgresql-normalized",
                    "source_range": f"{window_start}/{window_end}",
                    "record_count": str(row_count),
                    "generated_at": generated_at,
                    "git_sha": os.getenv("GIT_SHA", "unknown"),
                },
                content_type="application/vnd.apache.parquet",
                overwrite=args.overwrite,
            )
            exported_files += 1
            exported_rows += row_count
            print(
                f"PROCESSED WRITE dataset={args.dataset} rows={row_count} "
                f"bytes={result.size} path={result.path}"
            )

    print(
        f"PROCESSED EXPORT COMPLETE dataset={args.dataset} "
        f"files={exported_files} rows={exported_rows}"
    )


if __name__ == "__main__":
    main()
