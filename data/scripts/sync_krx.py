"""승인된 KRX 일별 데이터를 Raw Blob과 서비스 PostgreSQL에 동기화한다."""

from __future__ import annotations

import argparse
from datetime import date, datetime
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
    parser.add_argument("--date", required=True, help="KRX 기준일(YYYY-MM-DD)")
    parser.add_argument("--skip-blob", action="store_true", help="로컬 진단에서만 Raw Blob 업로드 생략")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Master를 먼저 적재한 뒤 같은 거래일 가격·지수를 하나의 transaction으로 반영한다."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    args = _parser().parse_args(argv)
    base_date = date.fromisoformat(args.date)
    base_date_text = base_date.strftime("%Y%m%d")
    client = KrxClient(
        os.getenv("KRX_AUTH_KEY", ""),
        base_url=os.getenv("KRX_BASE_URL", "https://data-dbg.krx.co.kr/svc/apis"),
        timeout_seconds=float(os.getenv("KRX_TIMEOUT_SECONDS", "10")),
    )
    raw = None if args.skip_blob else RawBlobWriter.from_env()
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
    print(
        f"KRX sync complete: date={base_date.isoformat()} "
        f"stocks={stocks} prices={prices} indices={indices}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
