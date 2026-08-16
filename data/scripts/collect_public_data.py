"""Collect Financial Services Commission public-data responses into Raw Blob only.

Azure Blob Storage is the authoritative Raw layer. This collector deliberately
has no PostgreSQL dependency; normalized/service tables are rebuilt separately
from canonical Raw objects.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from collectors.public_data_client import PublicDataApiError, PublicDataClient
from collectors.public_data_config import OPERATIONS, select_operations
from storage import RawBlobWriter


DEFAULT_DATASETS = ["stock_master", "stock_price", "market_index"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect data.go.kr FSC data into canonical monthly Raw Blob."
    )
    parser.add_argument(
        "--dataset",
        action="append",
        choices=sorted(OPERATIONS),
        help="Dataset to collect; repeat for multiple datasets.",
    )
    parser.add_argument("--all-datasets", action="store_true")
    parser.add_argument("--all-operations", action="store_true")
    parser.add_argument("--operation", action="append")
    parser.add_argument("--exclude-operation", action="append")
    dates = parser.add_mutually_exclusive_group()
    dates.add_argument("--date", type=date.fromisoformat)
    dates.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--rows", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--all-pages", action="store_true")
    parser.add_argument("--progress-every", type=int, default=10)
    return parser.parse_args()


def parse_item_date(value: object) -> date | None:
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def group_items_by_month(items: list[dict]) -> list[tuple[date, list[dict]]]:
    """Group one API page strictly by payload basDt without mutating payloads."""

    grouped: dict[date, list[dict]] = {}
    for index, item in enumerate(items):
        item_date = parse_item_date(item.get("basDt"))
        if item_date is None:
            raise ValueError(
                "Raw monthly partition requires a valid basDt; "
                f"record_index={index} basDt={item.get('basDt')!r}"
            )
        month = date(item_date.year, item_date.month, 1)
        grouped.setdefault(month, []).append(item)
    return sorted(grouped.items())


def _select_operations(args: argparse.Namespace):
    datasets = sorted(OPERATIONS) if args.all_datasets else (args.dataset or DEFAULT_DATASETS)
    operations = select_operations(datasets, include_all=args.all_operations)
    if args.operation:
        requested = set(args.operation)
        operations = [item for item in operations if item.name in requested]
        if missing := requested - {item.name for item in operations}:
            raise ValueError(f"Unknown operation for selected datasets: {sorted(missing)}")
    if args.exclude_operation:
        excluded = set(args.exclude_operation)
        available = {item.name for item in operations}
        if missing := excluded - available:
            raise ValueError(
                f"Unknown excluded operation for selected datasets: {sorted(missing)}"
            )
        operations = [item for item in operations if item.name not in excluded]
    return operations


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

    operations = _select_operations(args)
    if args.date:
        filters = {"basDt": args.date.strftime("%Y%m%d")}
    elif args.start_date:
        filters = {
            "beginBasDt": args.start_date.strftime("%Y%m%d"),
            "endBasDt": (args.end_date + timedelta(days=1)).strftime("%Y%m%d"),
        }
    else:
        filters = None

    client = PublicDataClient()
    raw_writer = RawBlobWriter.from_env()
    failures: list[str] = []
    total_received = 0

    for operation in operations:
        try:
            page_number = 1
            pages_processed = 0
            operation_received = 0
            written_records = 0
            while args.all_pages or pages_processed < args.max_pages:
                page = client.fetch_page(
                    operation,
                    page_number=page_number,
                    rows_per_page=args.rows,
                    filters=filters,
                )
                items = page.items
                if args.start_date:
                    items = [
                        item
                        for item in page.items
                        if (
                            (item_date := parse_item_date(item.get("basDt")))
                            and args.start_date <= item_date <= args.end_date
                        )
                    ]

                for partition_month, monthly_items in group_items_by_month(items):
                    _, batch = raw_writer.upload_items(
                        dataset=operation.dataset,
                        operation=operation.name,
                        items=monthly_items,
                        partition_date=partition_month,
                    )
                    written_records += batch.record_count

                pages_processed += 1
                operation_received += len(page.items)
                total_received += len(page.items)
                is_complete = not page.items or page_number * args.rows >= page.total_count
                if (
                    pages_processed == 1
                    or pages_processed % args.progress_every == 0
                    or is_complete
                ):
                    print(
                        f"{operation.dataset}/{operation.name}: page={page.page_number} "
                        f"received={operation_received} total={page.total_count} "
                        f"in_range={len(items)} raw_blob_records={written_records}"
                    )
                if is_complete:
                    break
                page_number += 1

            print(
                f"DONE {operation.dataset}/{operation.name}: "
                f"received={operation_received} pages={pages_processed}"
            )
        except Exception as error:
            message = str(error) if isinstance(error, (PublicDataApiError, ValueError)) else type(error).__name__
            failure = f"{operation.dataset}/{operation.name}: {message}"
            failures.append(failure)
            print(f"FAILED {failure}")

    print(
        f"collection complete: operations={len(operations)} "
        f"received={total_received} failures={len(failures)}"
    )
    if failures:
        raise PublicDataApiError("; ".join(failures))


if __name__ == "__main__":
    main()
