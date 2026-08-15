"""Export a bounded stock-price dataset to Parquet."""

import argparse
from datetime import date, datetime, timezone
import os
from pathlib import Path

from sqlalchemy import select

from db.connection import build_engine
from db.models import StockMaster, StockPriceDaily
from storage import BlobStorage, build_processed_path
from transforms import export_query_to_blob_parquet, export_query_to_parquet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, default=Path("exports/stock_prices.parquet"))
    parser.add_argument(
        "--blob", action="store_true", help="Upload to the processed Blob container."
    )
    parser.add_argument("--schema-version", default="1")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start > args.end:
        raise ValueError("--start must be on or before --end")
    query = (
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
        .where(StockPriceDaily.trade_date.between(args.start, args.end))
        .order_by(StockPriceDaily.trade_date, StockMaster.stock_code)
    )
    engine = build_engine()
    if args.blob:
        storage = BlobStorage.from_env()
        container = os.getenv("AZURE_STORAGE_CONTAINER_PROCESSED", "processed")
        path = build_processed_path(
            "stock_price",
            partition_date=args.start,
            file_name=f"stock-prices-{args.start}-{args.end}.parquet",
        )
        result = export_query_to_blob_parquet(
            engine,
            query,
            storage=storage,
            container=container,
            blob_path=path,
            metadata={
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_range": f"{args.start}/{args.end}",
                "schema_version": args.schema_version,
                "git_sha": os.getenv("GIT_SHA", "unknown"),
            },
        )
        print(f"exported: {result.container}/{result.path} bytes={result.size}")
    else:
        destination = export_query_to_parquet(engine, query, args.output)
        print(f"exported: {destination}")


if __name__ == "__main__":
    main()
