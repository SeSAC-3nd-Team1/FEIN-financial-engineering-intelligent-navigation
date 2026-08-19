"""canonical Raw Blob 경로만 읽어 operation별 월 보유기간을 점검한다."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import date
from typing import Iterable

from storage.blob import BlobStorage


RAW_PATH = re.compile(
    r"^data-go-kr/(?P<dataset>[a-z0-9._-]+)/operation=(?P<operation>[a-z0-9._-]+)/"
    r"year=(?P<year>\d{4})/month=(?P<month>\d{2})/[0-9a-f]{64}\.jsonl\.gz$"
)
DEFAULT_REQUIRED_OPERATIONS = (
    "stock_price/getstockpriceinfo",
    "market_index/getstockmarketindex",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit calendar-month coverage of canonical Raw Azure Blobs."
    )
    parser.add_argument("--minimum-years", type=int, default=5)
    parser.add_argument(
        "--require-operation",
        action="append",
        help=(
            "dataset/operation that must meet the minimum; repeat as needed. "
            "Defaults to stock price and stock market index."
        ),
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _month_index(value: date) -> int:
    return value.year * 12 + value.month - 1


def summarize_raw_coverage(
    paths: Iterable[str], *, minimum_years: int = 5
) -> list[dict[str, object]]:
    """Raw 경로를 operation별로 묶어 기간과 중간 누락 월을 계산한다.

    Blob의 월 partition은 ``payload.basDt``로 만들어지므로 전체 payload를 다시 내려받지
    않아도 보유 범위를 빠르게 감사할 수 있다. 이 검사는 required operation에 대해 최소
    기간뿐 아니라 첫 월부터 마지막 월까지 중간 누락 월이 없어야 통과하도록 설계한다.
    개별 거래일의 완전성까지 보증하지는 않는다.
    """

    if minimum_years < 1:
        raise ValueError("--minimum-years must be at least 1")

    grouped: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {"months": set(), "blob_count": 0}
    )
    for path in paths:
        match = RAW_PATH.fullmatch(path)
        if not match:
            continue
        month = date(int(match["year"]), int(match["month"]), 1)
        item = grouped[(match["dataset"], match["operation"])]
        item["months"].add(month)
        item["blob_count"] += 1

    summaries: list[dict[str, object]] = []
    for (dataset, operation), item in sorted(grouped.items()):
        months = sorted(item["months"])
        first, last = months[0], months[-1]
        month_span = _month_index(last) - _month_index(first)
        expected = set(range(_month_index(first), _month_index(last) + 1))
        observed = {_month_index(month) for month in months}
        missing_months = len(expected - observed)
        summaries.append(
            {
                "dataset": dataset,
                "operation": operation,
                "blob_count": item["blob_count"],
                "first_month": first.strftime("%Y-%m"),
                "last_month": last.strftime("%Y-%m"),
                "month_span": month_span,
                "observed_months": len(months),
                "missing_months": missing_months,
                "meets_minimum_years": (
                    month_span >= minimum_years * 12 and missing_months == 0
                ),
            }
        )
    return summaries


def assert_required_coverage(
    summaries: list[dict[str, object]], required_operations: Iterable[str]
) -> None:
    """핵심 시계열 operation이 최소 기간 또는 연속 월 조건을 어기면 실패시킨다."""

    indexed = {
        f"{item['dataset']}/{item['operation']}": item for item in summaries
    }
    failures: list[str] = []
    for required in required_operations:
        item = indexed.get(required.lower())
        if item is None:
            failures.append(f"{required}: not found")
        elif not item["meets_minimum_years"]:
            failures.append(
                f"{required}: {item['first_month']}..{item['last_month']} "
                f"({item['month_span']} months, "
                f"missing_months={item['missing_months']})"
            )
    if failures:
        raise RuntimeError("minimum Raw coverage not met: " + "; ".join(failures))


def main() -> None:
    args = parse_args()
    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    summaries = summarize_raw_coverage(
        storage.list_paths(container, prefix="data-go-kr/"),
        minimum_years=args.minimum_years,
    )
    required = args.require_operation or list(DEFAULT_REQUIRED_OPERATIONS)
    assert_required_coverage(summaries, required)

    if args.json:
        print(json.dumps(summaries, ensure_ascii=False, indent=2))
    else:
        for item in summaries:
            print(
                "RAW COVERAGE "
                f"dataset={item['dataset']} operation={item['operation']} "
                f"range={item['first_month']}..{item['last_month']} "
                f"span_months={item['month_span']} blobs={item['blob_count']} "
                f"missing_months={item['missing_months']} "
                f"minimum_ok={str(item['meets_minimum_years']).lower()}"
            )
        print(
            f"RAW COVERAGE OK minimum_years={args.minimum_years} "
            f"required={','.join(required)}"
        )


if __name__ == "__main__":
    main()
