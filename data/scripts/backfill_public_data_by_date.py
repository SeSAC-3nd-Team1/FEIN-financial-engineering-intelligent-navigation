"""장기간 범위 요청이 불안정한 operation을 일자 단위 병렬 호출로 Raw에 백필한다."""

from __future__ import annotations

import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta

from collectors.public_data_client import PublicDataClient, get_public_data_api_key
from collectors.public_data_config import OPERATIONS, ApiOperation
from scripts.collect_public_data import filter_items_by_date_range, group_items_by_month
from storage import RawBlobWriter


@dataclass(frozen=True)
class DateCollectionResult:
    """한 기준일의 API 조회와 Raw Blob 적재 결과를 표현한다."""

    target_date: date
    received: int
    in_range: int
    raw_blob_records: int
    created_blobs: int
    reused_blobs: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill one data.go.kr operation by independent basDt requests."
    )
    parser.add_argument("--dataset", required=True, choices=sorted(OPERATIONS))
    parser.add_argument("--operation", required=True)
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--progress-every", type=int, default=25)
    return parser.parse_args()


def iter_dates(start_date: date, end_date: date) -> list[date]:
    """양 끝 날짜를 포함한 일자 목록을 반환한다."""

    if start_date > end_date:
        raise ValueError("--start-date must not be after --end-date")
    day_count = (end_date - start_date).days + 1
    return [start_date + timedelta(days=offset) for offset in range(day_count)]


def resolve_operation(dataset: str, operation_name: str) -> ApiOperation:
    """dataset 안의 operation을 대소문자 구분 없이 하나로 확정한다."""

    matches = [
        operation
        for operation in OPERATIONS[dataset]
        if operation.name.lower() == operation_name.lower()
    ]
    if not matches:
        raise ValueError(f"Unknown operation for {dataset}: {operation_name}")
    return matches[0]


def collect_date(
    operation: ApiOperation,
    target_date: date,
    *,
    client: PublicDataClient,
    writer: RawBlobWriter,
    rows_per_page: int,
) -> DateCollectionResult:
    """operation의 하루치 전체 page를 읽어 원문 payload만 Raw Blob에 적재한다."""

    page_number = 1
    received = 0
    in_range = 0
    raw_blob_records = 0
    created_blobs = 0
    reused_blobs = 0
    filters = {"basDt": target_date.strftime("%Y%m%d")}

    while True:
        page = client.fetch_page(
            operation,
            page_number=page_number,
            rows_per_page=rows_per_page,
            filters=filters,
        )
        items = filter_items_by_date_range(
            page.items,
            start_date=target_date,
            end_date=target_date,
        )
        for partition_month, monthly_items in group_items_by_month(items):
            blob, batch = writer.upload_items(
                dataset=operation.dataset,
                operation=operation.name,
                items=monthly_items,
                partition_date=partition_month,
            )
            raw_blob_records += batch.record_count
            if blob.created:
                created_blobs += 1
            else:
                reused_blobs += 1

        received += len(page.items)
        in_range += len(items)
        if not page.items or page_number * rows_per_page >= page.total_count:
            break
        page_number += 1

    return DateCollectionResult(
        target_date=target_date,
        received=received,
        in_range=in_range,
        raw_blob_records=raw_blob_records,
        created_blobs=created_blobs,
        reused_blobs=reused_blobs,
    )


def main() -> None:
    args = parse_args()
    if args.rows < 1 or args.rows > 10_000:
        raise ValueError("--rows must be between 1 and 10000")
    if args.workers < 1 or args.workers > 16:
        raise ValueError("--workers must be between 1 and 16")
    if args.progress_every < 1:
        raise ValueError("--progress-every must be at least 1")

    operation = resolve_operation(args.dataset, args.operation)
    target_dates = iter_dates(args.start_date, args.end_date)
    api_key = get_public_data_api_key()
    writer = RawBlobWriter.from_env()
    thread_state = threading.local()

    def run_one(target_date: date) -> DateCollectionResult:
        # requests.Session을 thread 간 공유하지 않아 connection pool의 race를 피한다.
        if not hasattr(thread_state, "client"):
            thread_state.client = PublicDataClient(api_key=api_key)
        return collect_date(
            operation,
            target_date,
            client=thread_state.client,
            writer=writer,
            rows_per_page=args.rows,
        )

    totals = {
        "received": 0,
        "in_range": 0,
        "raw_blob_records": 0,
        "created_blobs": 0,
        "reused_blobs": 0,
    }
    failures: list[str] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_one, day): day for day in target_dates}
        for future in as_completed(futures):
            target_date = futures[future]
            try:
                result = future.result()
            except Exception as error:
                # 외부 예외의 URL에 serviceKey가 포함될 수 있으므로 타입만 기록한다.
                failures.append(f"{target_date.isoformat()}:{type(error).__name__}")
            else:
                for key in totals:
                    totals[key] += getattr(result, key)
            completed += 1
            if completed == 1 or completed % args.progress_every == 0:
                print(
                    f"DATE BACKFILL progress={completed}/{len(target_dates)} "
                    f"in_range={totals['in_range']} failures={len(failures)}"
                )

    print(
        f"DATE BACKFILL COMPLETE dataset={operation.dataset} "
        f"operation={operation.name} dates={len(target_dates)} "
        f"received={totals['received']} in_range={totals['in_range']} "
        f"raw_blob_records={totals['raw_blob_records']} "
        f"created_blobs={totals['created_blobs']} "
        f"reused_blobs={totals['reused_blobs']} failures={len(failures)}"
    )
    if failures:
        preview = ", ".join(failures[:20])
        raise RuntimeError(f"date backfill failures ({len(failures)}): {preview}")


if __name__ == "__main__":
    main()
