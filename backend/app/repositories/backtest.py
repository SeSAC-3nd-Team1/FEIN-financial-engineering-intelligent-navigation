"""백테스트에 필요한 시점 기준 KRX 종목·가격·지수·재무정보 조회."""

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Company,
    CompanyDisclosure,
    CompanyFinancial,
    MarketIndex,
    MarketStockPrice,
    Strategy,
)


REPORT_MONTHS_BEFORE_FY = {
    "11013": 9,
    "11012": 6,
    "11014": 3,
    "11011": 0,
}
REPORT_DISCLOSURE_KEYWORDS = {
    "11013": "분기보고서",
    "11012": "반기보고서",
    "11014": "분기보고서",
    "11011": "사업보고서",
}
REPORT_PERIOD_RE = re.compile(r"\((\d{4})\.(\d{2})\)")


@dataclass(frozen=True)
class StockPricePoint:
    stock_code: str
    trade_date: date
    close: Decimal
    listed_shares: int | None = None
    market_cap: Decimal | None = None


@dataclass(frozen=True)
class IndexPricePoint:
    trade_date: date
    close: Decimal


@dataclass(frozen=True)
class PointInTimeFinancial:
    stock_code: str
    available_at: date
    business_year: str
    report_code: str
    fs_div: str
    total_equity: Decimal
    net_income: Decimal | None = None


def financial_period_end(
    business_year: str,
    report_code: str,
    accounting_month: str | None,
) -> date | None:
    """사업연도·결산월·보고서코드로 해당 재무기간 종료일을 계산한다."""

    months_before = REPORT_MONTHS_BEFORE_FY.get(report_code)
    if months_before is None:
        return None
    try:
        fiscal_year = int(business_year)
        fiscal_month = int(accounting_month or "12")
    except (TypeError, ValueError):
        return None
    if fiscal_month < 1 or fiscal_month > 12:
        return None

    month_index = fiscal_year * 12 + (fiscal_month - 1) - months_before
    period_year, zero_based_month = divmod(month_index, 12)
    period_month = zero_based_month + 1
    last_day = calendar.monthrange(period_year, period_month)[1]
    return date(period_year, period_month, last_day)


def disclosure_matches_financial_period(
    report_name: str,
    report_code: str,
    period_end: date,
) -> bool:
    """공시명이 재무 보고서 종류와 회계기간에 명확히 대응할 때만 허용한다."""

    keyword = REPORT_DISCLOSURE_KEYWORDS.get(report_code)
    if not keyword or keyword not in report_name:
        return False

    # 기간 표기가 없는 공시는 다른 분기와의 구분이 모호하므로 자동 연결하지 않는다.
    period_match = REPORT_PERIOD_RE.search(report_name)
    if period_match is None:
        return False
    return (
        int(period_match.group(1)) == period_end.year
        and int(period_match.group(2)) == period_end.month
    )


class BacktestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def strategy(self, strategy_id: str) -> Strategy | None:
        return self.session.scalar(
            select(Strategy).where(Strategy.id == strategy_id, Strategy.is_active.is_(True))
        )

    def available_dates(
        self,
        *,
        min_stocks: int,
    ) -> tuple[date | None, date | None, date | None, date | None]:
        eligible_stock_dates = (
            select(MarketStockPrice.trade_date)
            .where(MarketStockPrice.market_cap.is_not(None), MarketStockPrice.market_cap > 0)
            .group_by(MarketStockPrice.trade_date)
            .having(func.count(func.distinct(MarketStockPrice.stock_code)) >= min_stocks)
            .subquery()
        )
        stock_min, stock_max = self.session.execute(
            select(
                func.min(eligible_stock_dates.c.trade_date),
                func.max(eligible_stock_dates.c.trade_date),
            )
        ).one()
        index_min, index_max = self.session.execute(
            select(func.min(MarketIndex.trade_date), func.max(MarketIndex.trade_date)).where(
                MarketIndex.market == "KOSPI",
                MarketIndex.index_name.in_(("코스피", "KOSPI")),
            )
        ).one()
        return stock_min, stock_max, index_min, index_max

    def universe_codes(self, as_of: date, *, limit: int = 100) -> list[str]:
        """시작일 전에 관측된 최신 시총으로 universe를 고정해 미래 universe 참조를 막는다."""

        latest_date = self.session.scalar(
            select(func.max(MarketStockPrice.trade_date)).where(MarketStockPrice.trade_date < as_of)
        )
        if latest_date is None:
            return []
        return list(self.session.scalars(
            select(MarketStockPrice.stock_code)
            .where(
                MarketStockPrice.trade_date == latest_date,
                MarketStockPrice.market_cap.is_not(None),
                MarketStockPrice.market_cap > 0,
            )
            .order_by(MarketStockPrice.market_cap.desc())
            .limit(limit)
        ))

    def stock_prices(self, stock_codes: list[str], start_date: date, end_date: date) -> list[StockPricePoint]:
        rows = self.session.execute(
            select(
                MarketStockPrice.stock_code,
                MarketStockPrice.trade_date,
                MarketStockPrice.close_price,
                MarketStockPrice.listed_shares,
                MarketStockPrice.market_cap,
            ).where(
                MarketStockPrice.stock_code.in_(stock_codes),
                MarketStockPrice.trade_date >= start_date,
                MarketStockPrice.trade_date <= end_date,
            ).order_by(MarketStockPrice.trade_date, MarketStockPrice.stock_code)
        )
        return [
            StockPricePoint(
                stock_code=code,
                trade_date=trade_date,
                close=close,
                listed_shares=listed_shares,
                market_cap=market_cap,
            )
            for code, trade_date, close, listed_shares, market_cap in rows
        ]

    def point_in_time_financials(
        self,
        stock_codes: list[str],
        end_date: date,
    ) -> list[PointInTimeFinancial]:
        """현재 재무 요약을 모든 확인된 정정공시 이후에만 사용 가능하게 만든다.

        OpenDART 재무 API에는 receipt_no/rcept_dt가 없고 현재 적재된 요약값은 정정된
        수치를 포함할 수 있다. 따라서 같은 회계기간의 공시 중 가장 늦은 접수일을
        ``available_at``으로 사용한다. 기간 표기가 없거나 연결이 모호한 행은 제외한다.
        이 방식은 가용 시점을 늦출 수 있지만 미래정보 누수보다 보수적이다.
        """

        if not stock_codes:
            return []

        financial_rows = list(self.session.execute(
            select(
                CompanyFinancial,
                Company.accounting_month,
                Company.stock_code,
            )
            .join(Company, Company.corp_code == CompanyFinancial.corp_code)
            .where(
                func.coalesce(CompanyFinancial.stock_code, Company.stock_code).in_(stock_codes),
                CompanyFinancial.total_equity.is_not(None),
            )
        ))
        if not financial_rows:
            return []

        corp_codes = sorted({financial.corp_code for financial, _, _ in financial_rows})
        disclosures = list(self.session.scalars(
            select(CompanyDisclosure)
            .where(
                CompanyDisclosure.corp_code.in_(corp_codes),
                or_(
                    CompanyDisclosure.report_name.ilike("%사업보고서%"),
                    CompanyDisclosure.report_name.ilike("%반기보고서%"),
                    CompanyDisclosure.report_name.ilike("%분기보고서%"),
                ),
            )
            .order_by(
                CompanyDisclosure.corp_code,
                CompanyDisclosure.receipt_date,
                CompanyDisclosure.receipt_no,
            )
        ))
        disclosures_by_corp: dict[str, list[CompanyDisclosure]] = defaultdict(list)
        for disclosure in disclosures:
            disclosures_by_corp[disclosure.corp_code].append(disclosure)

        selected: dict[tuple[str, str, str], tuple[int, PointInTimeFinancial]] = {}
        for financial, accounting_month, company_stock_code in financial_rows:
            stock_code = financial.stock_code or company_stock_code
            if not stock_code or financial.total_equity is None or financial.total_equity <= 0:
                continue
            period_end = financial_period_end(
                financial.business_year,
                financial.report_code,
                accounting_month,
            )
            if period_end is None:
                continue

            matching_receipts = [
                disclosure.receipt_date
                for disclosure in disclosures_by_corp.get(financial.corp_code, [])
                if disclosure.receipt_date > period_end
                and disclosure_matches_financial_period(
                    disclosure.report_name,
                    financial.report_code,
                    period_end,
                )
            ]
            if not matching_receipts:
                continue
            available_at = max(matching_receipts)
            if available_at > end_date:
                continue

            point = PointInTimeFinancial(
                stock_code=stock_code,
                available_at=available_at,
                business_year=financial.business_year,
                report_code=financial.report_code,
                fs_div=financial.fs_div,
                total_equity=financial.total_equity,
                net_income=financial.net_income,
            )
            key = (stock_code, financial.business_year, financial.report_code)
            priority = 0 if financial.fs_div == "CFS" else 1
            previous = selected.get(key)
            if previous is None or priority < previous[0]:
                selected[key] = (priority, point)

        return sorted(
            (point for _, point in selected.values()),
            key=lambda item: (item.stock_code, item.available_at, item.business_year, item.report_code),
        )

    def kospi_prices(self, start_date: date, end_date: date) -> list[IndexPricePoint]:
        rows = self.session.execute(
            select(MarketIndex.trade_date, MarketIndex.close_value)
            .where(
                MarketIndex.market == "KOSPI",
                MarketIndex.index_name.in_(("코스피", "KOSPI")),
                MarketIndex.trade_date >= start_date,
                MarketIndex.trade_date <= end_date,
            )
            .order_by(MarketIndex.trade_date)
        )
        unique = {trade_date: IndexPricePoint(trade_date, close) for trade_date, close in rows}
        return [unique[key] for key in sorted(unique)]
