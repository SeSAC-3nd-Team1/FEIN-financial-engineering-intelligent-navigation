"""Export a bounded stock-price dataset to Parquet."""

import argparse
from datetime import date
from pathlib import Path

from sqlalchemy import select

from db.connection import build_engine
from db.models import StockMaster, StockPriceDaily
from transforms import export_query_to_parquet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, default=Path("exports/stock_prices.parquet"))
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
    destination = export_query_to_parquet(build_engine(), query, args.output)
    print(f"exported: {destination}")


if __name__ == "__main__":
    main()
