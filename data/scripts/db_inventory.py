"""Print a compact inventory for the currently configured PostgreSQL database."""

from __future__ import annotations

import argparse

from sqlalchemy import text

from db.connection import build_engine


TABLES = (
    "stock_master",
    "stock_price_daily",
    "market_index_daily",
    "stock_issuance",
    "financial_statement",
    "macro_indicator",
    "public_data_record",
    "public_data_collection_checkpoint",
    "data_object",
    "public_data_migration_manifest",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--exact",
        action="store_true",
        help="Full-scan the large landing table and print exact dataset counts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    engine = build_engine()
    with engine.connect() as connection:
        version = connection.scalar(text("SHOW server_version"))
        size = connection.scalar(
            text("SELECT pg_size_pretty(pg_database_size(current_database()))")
        )
        print(f"server_version={version} database_size={size}")

        for table_name in TABLES:
            if table_name == "public_data_record" and not args.exact:
                count = connection.scalar(
                    text(
                        "SELECT reltuples::bigint FROM pg_class "
                        "WHERE oid='raw.public_data_record'::regclass"
                    )
                )
                print(f"table raw.{table_name} estimated_rows={count}")
            else:
                count = connection.scalar(
                    text(f'SELECT count(*) FROM raw."{table_name}"')
                )
                print(f"table raw.{table_name} rows={count}")

        if args.exact:
            datasets = connection.execute(
                text(
                    "SELECT dataset, count(*) FROM raw.public_data_record "
                    "GROUP BY dataset ORDER BY dataset"
                )
            )
            for dataset, count in datasets:
                print(f"dataset {dataset} rows={count}")
        else:
            print("dataset counts skipped; use --exact for a full landing-table scan")

        checkpoints = connection.execute(
            text(
                "SELECT range_start, range_end, status, count(*) "
                "FROM raw.public_data_collection_checkpoint "
                "GROUP BY range_start, range_end, status "
                "ORDER BY range_start, range_end, status"
            )
        )
        for start, end, status, count in checkpoints:
            print(f"checkpoint {start}..{end} status={status} operations={count}")


if __name__ == "__main__":
    main()
