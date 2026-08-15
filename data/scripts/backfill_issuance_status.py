"""Backfill issuance-status snapshots by known trading day.

The portal times out for range queries on getStocIssuStat_V3, while exact basDt
queries are stable. This runner uses already-loaded stock-price trading dates and
stores a checkpoint after every day.
"""

from __future__ import annotations

import argparse
from datetime import date

from sqlalchemy import select

from collectors.public_data_client import PublicDataClient
from collectors.public_data_config import OPERATIONS
from db.connection import build_engine, session_scope
from db.models import PublicDataCollectionCheckpoint, StockPriceDaily
from loaders.public_data import record_raw_data_object
from storage import RawBlobWriter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--progress-every", type=int, default=25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    operation = next(
        item
        for item in OPERATIONS["stock_issuance"]
        if item.name == "getStocIssuStat_V3"
    )
    engine = build_engine()
    client = PublicDataClient()
    raw_writer = RawBlobWriter.from_env()

    with session_scope(engine) as session:
        trading_dates = list(
            session.scalars(
                select(StockPriceDaily.trade_date)
                .where(
                    StockPriceDaily.trade_date >= args.start_date,
                    StockPriceDaily.trade_date <= args.end_date,
                )
                .distinct()
                .order_by(StockPriceDaily.trade_date)
            )
        )
        checkpoint = session.scalar(
            select(PublicDataCollectionCheckpoint).where(
                PublicDataCollectionCheckpoint.dataset == operation.dataset,
                PublicDataCollectionCheckpoint.operation == operation.name,
                PublicDataCollectionCheckpoint.range_start == args.start_date,
                PublicDataCollectionCheckpoint.range_end == args.end_date,
            )
        )
        if checkpoint is None:
            checkpoint = PublicDataCollectionCheckpoint(
                dataset=operation.dataset,
                operation=operation.name,
                range_start=args.start_date,
                range_end=args.end_date,
                rows_per_page=args.rows,
                next_page=1,
                received_count=0,
                status="pending",
            )
            session.add(checkpoint)
            session.flush()
        start_index = checkpoint.next_page - 1
        checkpoint.rows_per_page = args.rows
        checkpoint.total_count = len(trading_dates)
        checkpoint.status = "running"
        checkpoint.last_error = None

    for index in range(start_index, len(trading_dates)):
        trade_date = trading_dates[index]
        received = 0
        page_number = 1
        while True:
            page = client.fetch_page(
                operation,
                page_number=page_number,
                rows_per_page=args.rows,
                filters={"basDt": trade_date.strftime("%Y%m%d")},
            )
            blob_result = None
            if page.items:
                blob_result = raw_writer.upload_items(
                    dataset=operation.dataset,
                    operation=operation.name,
                    items=page.items,
                    partition_date=trade_date,
                    page_number=page_number,
                )
            with session_scope(engine) as session:
                if blob_result:
                    blob, batch = blob_result
                    record_raw_data_object(
                        session,
                        operation,
                        blob,
                        batch,
                        source=raw_writer.source,
                        range_start=trade_date,
                        range_end=trade_date,
                    )
            received += len(page.items)
            if not page.items or received >= page.total_count:
                break
            page_number += 1

        with session_scope(engine) as session:
            checkpoint = session.scalar(
                select(PublicDataCollectionCheckpoint).where(
                    PublicDataCollectionCheckpoint.dataset == operation.dataset,
                    PublicDataCollectionCheckpoint.operation == operation.name,
                    PublicDataCollectionCheckpoint.range_start == args.start_date,
                    PublicDataCollectionCheckpoint.range_end == args.end_date,
                )
            )
            checkpoint.next_page = index + 2
            checkpoint.received_count += received
            checkpoint.status = (
                "complete" if index + 1 == len(trading_dates) else "running"
            )

        if index == start_index or (index + 1) % args.progress_every == 0:
            print(
                f"issuance status: trading_day={index + 1}/{len(trading_dates)} "
                f"date={trade_date} received={received}"
            )

    print(
        f"issuance status complete: trading_days={len(trading_dates)} "
        f"range={args.start_date}..{args.end_date}"
    )


if __name__ == "__main__":
    main()
