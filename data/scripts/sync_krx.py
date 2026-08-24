"""승인된 KRX 일별 데이터를 Raw Blob과 서비스 PostgreSQL에 동기화한다."""

from __future__ import annotations

from collections.abc import Iterator
import argparse
from datetime import date, datetime, timedelta
import os

from dotenv import load_dotenv

from collectors.krx_client import KrxClient
from collectors.krx_config import OPERATIONS
from db.connection.session import PROJECT_ROOT, session_scope
from loaders.krx import KrxRepository
from processing.krx import market_index_rows, stock_master_rows, stock_price_rows
from storage.raw import RawBlobWriter


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synchronize approved KRX OPEN API datasets")
    dates = parser.add_mutually_exclusive_group(required=True)
    dates.add_argument("--date", help="KRX 기준일(YYYY-MM-DD)")
    dates.add_argument("--start-date", help="KRX 백필 시작일(YYYY-MM-DD, 양끝 포함)")
    parser.add_argument("--end-date", help="KRX 백필 종료일(YYYY-MM-DD, 양끝 포함)")
    parser.add_argument("--skip-blob", action="store_true", help="로컬 진단에서만 Raw Blob 업로드 생략")
    return parser


def _sync_dates(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Iterator[date]:
    """단일 기준일 또는 양끝을 포함한 평일 백필 범위를 검증해 반환한다."""

    if args.date:
        if args.end_date:
            parser.error("--end-date can only be used with --start-date")
        yield date.fromisoformat(args.date)
        return
    if not args.end_date:
        parser.error("--end-date is required with --start-date")
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if start_date > end_date:
        parser.error("--start-date must not be after --end-date")

    current = start_date
    while current <= end_date:
        # KRX는 주말 거래 자료가 없으므로 불필요한 외부 요청만 건너뛴다. 휴장일은 API의 빈 응답을 그대로 따른다.
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def _sync_date(
    base_date: date,
    *,
    client: KrxClient,
    raw: RawBlobWriter | None,
) -> tuple[int, int, int]:
    """Master를 먼저 적재한 뒤 같은 거래일 가격·지수를 하나의 transaction으로 반영한다."""

    base_date_text = base_date.strftime("%Y%m%d")
    stock_rows: list[dict] = []
    price_rows: list[dict] = []
    index_rows: list[dict] = []

    for operation in OPERATIONS:
        items = client.fetch(operation, base_date_text)
        if raw and items:
            raw_writer = RawBlobWriter(raw.storage, container=raw.container, source="krx")
            raw_writer.upload_items(
                dataset=operation.dataset,
                operation=operation.name,
                items=items,
                partition_date=base_date,
                collected_at=datetime.now().astimezone(),
            )
        if operation.dataset == "stock_master":
            stock_rows.extend(stock_master_rows(items, market=operation.market, as_of=base_date))
        elif operation.dataset == "stock_price":
            price_rows.extend(stock_price_rows(items, market=operation.market, as_of=base_date))
        else:
            index_rows.extend(market_index_rows(items, market=operation.market, as_of=base_date))

    with session_scope() as session:
        repository = KrxRepository(session)
        stocks = repository.upsert_stocks(stock_rows)
        prices = repository.upsert_prices(price_rows)
        indices = repository.upsert_indices(index_rows)
    return stocks, prices, indices


def main(argv: list[str] | None = None) -> int:
    """날짜별 transaction으로 단일일 또는 과거 범위를 멱등 동기화한다."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    parser = _parser()
    args = parser.parse_args(argv)
    dates = list(_sync_dates(args, parser))
    client = KrxClient(
        os.getenv("KRX_AUTH_KEY", ""),
        base_url=os.getenv("KRX_BASE_URL", "https://data-dbg.krx.co.kr/svc/apis"),
        timeout_seconds=float(os.getenv("KRX_TIMEOUT_SECONDS", "10")),
    )
    raw = None if args.skip_blob else RawBlobWriter.from_env()

    for base_date in dates:
        stocks, prices, indices = _sync_date(base_date, client=client, raw=raw)
        print(
            f"KRX sync complete: date={base_date.isoformat()} "
            f"stocks={stocks} prices={prices} indices={indices}"
        )
    print(f"KRX sync range complete: dates={len(dates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
