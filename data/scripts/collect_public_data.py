"""Collect Financial Services Commission datasets into local PostgreSQL."""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from sqlalchemy import select

from collectors.public_data_client import PublicDataApiError, PublicDataClient
from collectors.public_data_config import OPERATIONS, select_operations
from db.connection import build_engine, session_scope
from db.models import PublicDataCollectionCheckpoint
from loaders.public_data import (
    load_landing_items,
    load_normalized_items,
    parse_date as parse_item_date,
)


DEFAULT_DATASETS = ["stock_master", "stock_price", "market_index"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect data.go.kr FSC data without exposing the API key."
    )
    parser.add_argument(
        "--dataset",
        action="append",
        choices=sorted(OPERATIONS),
        help="Dataset to collect; repeat for multiple datasets.",
    )
    parser.add_argument(
        "--all-datasets", action="store_true", help="Collect all eight datasets."
    )
    parser.add_argument(
        "--all-operations",
        action="store_true",
        help="Collect every operation, including all disclosure event types.",
    )
    parser.add_argument(
        "--operation",
        action="append",
        help="Limit collection to an exact operation name; repeat as needed.",
    )
    parser.add_argument(
        "--exclude-operation",
        action="append",
        help="Exclude an exact operation name; repeat as needed.",
    )
    dates = parser.add_mutually_exclusive_group()
    dates.add_argument(
        "--date", type=date.fromisoformat, help="Reference date in YYYY-MM-DD."
    )
    dates.add_argument(
        "--start-date",
        type=date.fromisoformat,
        help="Inclusive backfill start date in YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        help="Inclusive backfill end date; requires --start-date.",
    )
    parser.add_argument("--rows", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument(
        "--all-pages",
        action="store_true",
        help="Read every API page. Date-range runs resume from a DB checkpoint.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10,
        help="Print progress every N pages.",
    )
    parser.add_argument(
        "--raw-only", action="store_true", help="Skip normalized domain tables."
    )
    return parser.parse_args()


def get_checkpoint(session, operation, args):
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
    elif checkpoint.status != "complete" and checkpoint.rows_per_page != args.rows:
        raise ValueError(
            f"checkpoint uses --rows {checkpoint.rows_per_page}; "
            "resume with the same page size"
        )
    return checkpoint


def record_failure(engine, operation, args, message: str) -> None:
    if not args.start_date:
        return
    with session_scope(engine) as session:
        checkpoint = get_checkpoint(session, operation, args)
        checkpoint.status = "failed"
        checkpoint.last_error = message[:2_000]


def safe_error_message(error: Exception) -> str:
    """Keep logs concise and prevent request/SQL parameters from leaking."""

    if isinstance(error, (PublicDataApiError, ValueError)):
        return str(error)
    return type(error).__name__


def main() -> None:
    args = parse_args()
    if args.rows < 1 or args.rows > 10_000:
        raise ValueError("--rows must be between 1 and 10000")
    if args.max_pages < 1:
        raise ValueError("--max-pages must be at least 1")
    if args.progress_every < 1:
        raise ValueError("--progress-every must be at least 1")
    if bool(args.start_date) != bool(args.end_date):
        raise ValueError("--start-date and --end-date must be supplied together")
    if args.start_date and args.start_date > args.end_date:
        raise ValueError("--start-date must not be after --end-date")

    datasets = (
        sorted(OPERATIONS)
        if args.all_datasets
        else (args.dataset or DEFAULT_DATASETS)
    )
    operations = select_operations(datasets, include_all=args.all_operations)
    if args.operation:
        requested = set(args.operation)
        operations = [item for item in operations if item.name in requested]
        found = {item.name for item in operations}
        if missing := requested - found:
            raise ValueError(f"Unknown operation for selected datasets: {sorted(missing)}")
    if args.exclude_operation:
        excluded = set(args.exclude_operation)
        available = {item.name for item in operations}
        if missing := excluded - available:
            raise ValueError(
                f"Unknown excluded operation for selected datasets: {sorted(missing)}"
            )
        operations = [item for item in operations if item.name not in excluded]
    if args.date:
        filters = {"basDt": args.date.strftime("%Y%m%d")}
    elif args.start_date:
        # The portal defines endBasDt as exclusive.
        filters = {
            "beginBasDt": args.start_date.strftime("%Y%m%d"),
            "endBasDt": (args.end_date + timedelta(days=1)).strftime("%Y%m%d"),
        }
    else:
        filters = None
    client = PublicDataClient()
    engine = build_engine()
    failures: list[str] = []
    total_received = 0

    for operation in operations:
        try:
            start_page = 1
            if args.start_date:
                with session_scope(engine) as session:
                    checkpoint = get_checkpoint(session, operation, args)
                    if checkpoint.status == "complete":
                        print(
                            f"SKIP {operation.dataset}/{operation.name}: "
                            f"checkpoint complete rows={checkpoint.received_count}"
                        )
                        continue
                    start_page = checkpoint.next_page

            page_number = start_page
            pages_processed = 0
            operation_received = 0
            while args.all_pages or pages_processed < args.max_pages:
                page = client.fetch_page(
                    operation,
                    page_number=page_number,
                    rows_per_page=args.rows,
                    filters=filters,
                )
                items = page.items
                if args.start_date:
                    # Several disclosure operations ignore beginBasDt/endBasDt.
                    # Enforce the requested range before any DB write.
                    items = [
                        item
                        for item in page.items
                        if (
                            (item_date := parse_item_date(item.get("basDt")))
                            and args.start_date <= item_date <= args.end_date
                        )
                    ]
                is_complete = (
                    not page.items
                    or page_number * args.rows >= page.total_count
                )
                with session_scope(engine) as session:
                    raw_count = load_landing_items(session, operation, items)
                    # A range master backfill is retained in the landing table;
                    # do not let older snapshots overwrite the current master.
                    normalize_page = not args.raw_only and not (
                        args.start_date and operation.name == "getItemInfo"
                    )
                    normalized_count = (
                        load_normalized_items(session, operation, items)
                        if normalize_page
                        else 0
                    )
                    if args.start_date:
                        checkpoint = get_checkpoint(session, operation, args)
                        checkpoint.next_page = page_number + 1
                        checkpoint.total_count = page.total_count
                        checkpoint.received_count += len(page.items)
                        checkpoint.status = "complete" if is_complete else "running"
                        checkpoint.last_error = None

                pages_processed += 1
                page_number += 1
                operation_received += len(page.items)
                total_received += len(page.items)
                if (
                    pages_processed == 1
                    or pages_processed % args.progress_every == 0
                    or is_complete
                ):
                    print(
                        f"{operation.dataset}/{operation.name}: "
                        f"page={page.page_number} received={operation_received} "
                        f"total={page.total_count} in_range={len(items)} "
                        f"raw={raw_count} "
                        f"normalized={normalized_count}"
                    )
                if is_complete:
                    break

            print(
                f"DONE {operation.dataset}/{operation.name}: "
                f"run_received={operation_received} pages={pages_processed}"
            )
        except Exception as error:
            failure = (
                f"{operation.dataset}/{operation.name}: "
                f"{safe_error_message(error)}"
            )
            record_failure(engine, operation, args, failure)
            failures.append(failure)
            print(f"FAILED {failures[-1]}")

    print(
        f"collection complete: operations={len(operations)} "
        f"received={total_received} failures={len(failures)}"
    )
    if failures:
        raise PublicDataApiError("; ".join(failures))


if __name__ == "__main__":
    main()
