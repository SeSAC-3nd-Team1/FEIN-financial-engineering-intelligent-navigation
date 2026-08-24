"""KRX 화면 조회용 PostgreSQL 백필 범위와 적재 건수를 검증한다."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import distinct, func, select

from db.connection.session import session_scope
from db.models.market_data import MarketIndex, MarketStockPrice


@dataclass(frozen=True)
class Coverage:
    """한 KRX serving table의 요청 범위 내 적재 현황이다."""

    first_date: date | None
    last_date: date | None
    trading_days: int
    rows: int


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify KRX PostgreSQL backfill coverage")
    parser.add_argument("--start-date", required=True, help="검증 시작일(YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="검증 종료일(YYYY-MM-DD)")
    return parser


def _is_complete(coverage: Coverage, start_date: date, end_date: date) -> bool:
    """주말·연휴를 허용하면서 요청 범위 양 끝에 실제 거래 데이터가 있는지 판정한다."""

    if not coverage.first_date or not coverage.last_date or coverage.rows <= 0:
        return False
    boundary_tolerance = timedelta(days=7)
    return (
        coverage.first_date <= start_date + boundary_tolerance
        and coverage.last_date >= end_date - boundary_tolerance
        and coverage.trading_days > 0
    )


def _coverage(
    model: type[MarketStockPrice] | type[MarketIndex], start: date, end: date
) -> Coverage:
    """지정 테이블의 기간 경계, 거래일 수, 전체 행 수를 한 번에 조회한다."""

    trade_date = model.trade_date
    with session_scope() as session:
        row = session.execute(
            select(
                func.min(trade_date),
                func.max(trade_date),
                func.count(distinct(trade_date)),
                func.count(),
            ).where(trade_date.between(start, end))
        ).one()
    return Coverage(
        first_date=row[0],
        last_date=row[1],
        trading_days=int(row[2] or 0),
        rows=int(row[3] or 0),
    )


def main(argv: list[str] | None = None) -> int:
    """종목 가격과 시장 지수가 요청 기간을 모두 덮는지 확인한다."""

    args = _parser().parse_args(argv)
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if start_date > end_date:
        raise SystemExit("--start-date must not be after --end-date")

    results = {
        "stock_prices": _coverage(MarketStockPrice, start_date, end_date),
        "market_indices": _coverage(MarketIndex, start_date, end_date),
    }
    failed: list[str] = []
    for name, coverage in results.items():
        print(
            f"KRX coverage: table={name} first_date={coverage.first_date} "
            f"last_date={coverage.last_date} trading_days={coverage.trading_days} "
            f"rows={coverage.rows}"
        )
        if not _is_complete(coverage, start_date, end_date):
            failed.append(name)

    if failed:
        print(f"KRX coverage verification failed: tables={','.join(failed)}")
        return 1
    print("KRX coverage verification complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
