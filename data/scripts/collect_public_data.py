"""Collect Financial Services Commission datasets into local PostgreSQL."""

from __future__ import annotations

import argparse
from datetime import date

from collectors.public_data_client import PublicDataApiError, PublicDataClient
from collectors.public_data_config import OPERATIONS, select_operations
from db.connection import build_engine, session_scope
from loaders.public_data import load_landing_items, load_normalized_items


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
        "--date", type=date.fromisoformat, help="Reference date in YYYY-MM-DD."
    )
    parser.add_argument("--rows", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument(
        "--raw-only", action="store_true", help="Skip normalized domain tables."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.rows < 1 or args.rows > 10_000:
        raise ValueError("--rows must be between 1 and 10000")
    if args.max_pages < 1:
        raise ValueError("--max-pages must be at least 1")

    datasets = (
        sorted(OPERATIONS)
        if args.all_datasets
        else (args.dataset or DEFAULT_DATASETS)
    )
    operations = select_operations(datasets, include_all=args.all_operations)
    filters = {"basDt": args.date.strftime("%Y%m%d")} if args.date else None
    client = PublicDataClient()
    engine = build_engine()
    failures: list[str] = []
    total_received = 0

    for operation in operations:
        try:
            items = client.fetch_items(
                operation,
                rows_per_page=args.rows,
                max_pages=args.max_pages,
                filters=filters,
            )
            with session_scope(engine) as session:
                raw_count = load_landing_items(session, operation, items)
                normalized_count = (
                    0
                    if args.raw_only
                    else load_normalized_items(session, operation, items)
                )
            total_received += len(items)
            print(
                f"{operation.dataset}/{operation.name}: received={len(items)} "
                f"raw={raw_count} normalized={normalized_count}"
            )
        except Exception as error:
            failures.append(f"{operation.dataset}/{operation.name}: {error}")
            print(f"FAILED {failures[-1]}")

    print(
        f"collection complete: operations={len(operations)} "
        f"received={total_received} failures={len(failures)}"
    )
    if failures:
        raise PublicDataApiError("; ".join(failures))


if __name__ == "__main__":
    main()
