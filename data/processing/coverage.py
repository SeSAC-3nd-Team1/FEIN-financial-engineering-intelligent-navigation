"""시계열 데이터의 기간 경계와 내부 연속성을 검증하는 공통 유틸이다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from collections.abc import Iterable


@dataclass(frozen=True)
class TradingDateCoverage:
    """요청 기간 내 고유 거래일의 경계·밀도·최대 공백 요약이다."""

    first_date: date | None
    last_date: date | None
    trading_days: int
    weekday_days: int
    weekday_density: float
    max_gap_days: int


def _weekday_count(start_date: date, end_date: date) -> int:
    """주말만 제외한 평일 수를 보수적인 거래 가능일 분모로 계산한다."""

    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    return sum(
        1
        for offset in range((end_date - start_date).days + 1)
        if (start_date + timedelta(days=offset)).weekday() < 5
    )


def summarize_trading_dates(
    values: Iterable[date],
    *,
    start_date: date,
    end_date: date,
) -> TradingDateCoverage:
    """중복을 제거한 실제 거래일로 경계·평일 대비 밀도·최대 내부 공백을 계산한다."""

    unique_dates = tuple(sorted({value for value in values if start_date <= value <= end_date}))
    weekday_days = _weekday_count(start_date, end_date)
    max_gap_days = 0
    if len(unique_dates) >= 2:
        max_gap_days = max(
            (current - previous).days
            for previous, current in zip(unique_dates, unique_dates[1:])
        )
    return TradingDateCoverage(
        first_date=unique_dates[0] if unique_dates else None,
        last_date=unique_dates[-1] if unique_dates else None,
        trading_days=len(unique_dates),
        weekday_days=weekday_days,
        weekday_density=(len(unique_dates) / weekday_days) if weekday_days else 0.0,
        max_gap_days=max_gap_days,
    )


def coverage_is_complete(
    coverage: TradingDateCoverage,
    *,
    start_date: date,
    end_date: date,
    boundary_tolerance_days: int = 7,
    minimum_weekday_density: float = 0.8,
    maximum_gap_days: int = 14,
) -> bool:
    """정상 휴장일은 허용하면서 장기·중간 누락은 실패로 판정한다.

    국내 증시는 공휴일 때문에 모든 평일에 거래하지 않으므로 평일 대비 80% 이상을
    요구하고, 설·추석 같은 연휴를 고려해 내부 최대 달력일 공백은 14일까지 허용한다.
    """

    if coverage.first_date is None or coverage.last_date is None:
        return False
    tolerance = timedelta(days=boundary_tolerance_days)
    return (
        coverage.first_date <= start_date + tolerance
        and coverage.last_date >= end_date - tolerance
        and coverage.weekday_density >= minimum_weekday_density
        and coverage.max_gap_days <= maximum_gap_days
    )
