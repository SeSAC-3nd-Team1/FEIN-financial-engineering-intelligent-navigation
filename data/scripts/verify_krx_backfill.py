"""KRX 화면 조회용 PostgreSQL 백필 범위와 적재 건수를 검증한다."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select

from db.connection.session import session_scope
from db.models.market_data import MarketIndex, MarketStockPrice


@dataclass(frozen=True)
class Coverage:
    """한 KRX serving table의 요청 범위 내 적재 현황이다."""

    trade_dates: tuple[date, ...]
    rows: int

    @property
    def first_date(self) -> date | None:
        return self.trade_dates[0] if self.trade_dates else None

    @property
    def last_date(self) -> date | None:
        return self.trade_dates[-1] if self.trade_dates else None

    @property
    def trading_days(self) -> int:
        return len(self.trade_dates)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify KRX PostgreSQL backfill coverage")
    parser.add_argument("--start-date", required=True, help="검증 시작일(YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="검증 종료일(YYYY-MM-DD)")
    return parser


def _weekday_count(start_date: date, end_date: date) -> int:
    """요청 구간의 평일 수를 계산해 거래일 밀도의 보수적인 분모로 사용한다."""

    return sum(
        1
        for offset in range((end_date - start_date).days + 1)
        if (start_date + timedelta(days=offset)).weekday() < 5
    )


def _max_gap_days(trade_dates: tuple[date, ...]) -> int:
    """정렬된 실제 거래일 사이의 가장 긴 달력일 공백을 반환한다."""

    if len(trade_dates) < 2:
        return 0
    return max(
        (current - previous).days
        for previous, current in zip(trade_dates, trade_dates[1:])
    )


def _coverage_metrics(
    coverage: Coverage, start_date: date, end_date: date
) -> tuple[float, int]:
    """평일 대비 적재 밀도와 내부 최대 공백을 계산한다."""

    weekdays = _weekday_count(start_date, end_date)
    density = coverage.trading_days / weekdays if weekdays else 0.0
    return density, _max_gap_days(coverage.trade_dates)


def _is_complete(coverage: Coverage, start_date: date, end_date: date) -> bool:
    """범위 경계뿐 아니라 거래일 밀도와 중간 연속성까지 검증한다."""

    if not coverage.first_date or not coverage.last_date or coverage.rows <= 0:
        return False
    boundary_tolerance = timedelta(days=7)
    density, max_gap_days = _coverage_metrics(coverage, start_date, end_date)
    # 국내 증시의 정상 연휴는 허용하되 월·연 단위 누락은 밀도와 최대 공백으로 함께 차단한다.
    return (
        coverage.first_date <= start_date + boundary_tolerance
        and coverage.last_date >= end_date - boundary_tolerance
        and density >= 0.8
        and max_gap_days <= 14
    )


def _coverage(
    model: type[MarketStockPrice] | type[MarketIndex], start: date, end: date
) -> Coverage:
    """지정 테이블의 실제 거래일 목록과 전체 행 수를 조회한다."""

    trade_date = model.trade_date
    with session_scope() as session:
        trade_dates = tuple(
            session.scalars(
                select(trade_date)
                .where(trade_date.between(start, end))
                .distinct()
                .order_by(trade_date)
            ).all()
        )
        rows = session.scalar(
            select(func.count()).select_from(model).where(trade_date.between(start, end))
        )
    return Coverage(
        trade_dates=trade_dates,
        rows=int(rows or 0),
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
        density, max_gap_days = _coverage_metrics(coverage, start_date, end_date)
        print(
            f"KRX coverage: table={name} first_date={coverage.first_date} "
            f"last_date={coverage.last_date} trading_days={coverage.trading_days} "
            f"weekday_density={density:.3f} max_gap_days={max_gap_days} rows={coverage.rows}"
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
