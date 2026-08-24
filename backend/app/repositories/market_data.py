"""KRX 종목·일별시세와 OpenDART 최신 연간 재무 조회."""

from datetime import date

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models import Company, CompanyFinancial, MarketIndex, MarketStock, MarketStockPrice


class MarketDataRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def stock(self, stock_code: str) -> MarketStock | None:
        return self.session.get(MarketStock, stock_code)

    def latest_price(self, stock_code: str) -> MarketStockPrice | None:
        return self.session.scalar(
            select(MarketStockPrice)
            .where(MarketStockPrice.stock_code == stock_code)
            .order_by(MarketStockPrice.trade_date.desc())
            .limit(1)
        )

    def prices_since(self, stock_code: str, start_date: date) -> list[MarketStockPrice]:
        return list(self.session.scalars(
            select(MarketStockPrice)
            .where(
                MarketStockPrice.stock_code == stock_code,
                MarketStockPrice.trade_date >= start_date,
            )
            .order_by(MarketStockPrice.trade_date)
        ))

    def kospi_since(self, start_date: date | None) -> list[MarketIndex]:
        query = select(MarketIndex).where(
            MarketIndex.market == "KOSPI",
            MarketIndex.index_name.in_(("코스피", "KOSPI")),
        )
        if start_date is not None:
            query = query.where(MarketIndex.trade_date >= start_date)
        rows = self.session.scalars(query.order_by(MarketIndex.trade_date, MarketIndex.id))
        unique = {row.trade_date: row for row in rows}
        return [unique[trade_date] for trade_date in sorted(unique)]

    def closing_prices(self, stock_code: str, effective_on: date) -> list[MarketStockPrice]:
        return list(self.session.scalars(
            select(MarketStockPrice)
            .where(
                MarketStockPrice.stock_code == stock_code,
                MarketStockPrice.trade_date <= effective_on,
            )
            .order_by(MarketStockPrice.trade_date.desc())
            .limit(2)
        ))

    def has_kospi_close(self, trade_date: date) -> bool:
        return self.session.scalar(
            select(MarketIndex.id).where(
                MarketIndex.market == "KOSPI",
                MarketIndex.index_name.in_(("코스피", "KOSPI")),
                MarketIndex.trade_date == trade_date,
            ).limit(1)
        ) is not None

    def company(self, stock_code: str) -> Company | None:
        return self.session.scalar(select(Company).where(Company.stock_code == stock_code))

    def latest_annual_financial(self, stock_code: str) -> CompanyFinancial | None:
        """PER/PBR/ROE의 기간 왜곡을 막기 위해 최신 FY를 CFS 우선으로 선택한다."""

        return self.session.scalar(
            select(CompanyFinancial)
            .where(CompanyFinancial.stock_code == stock_code, CompanyFinancial.quarter == "FY")
            .order_by(
                CompanyFinancial.business_year.desc(),
                case((CompanyFinancial.fs_div == "CFS", 0), else_=1),
                CompanyFinancial.updated_at.desc(),
            )
            .limit(1)
        )

