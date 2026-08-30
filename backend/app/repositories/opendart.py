"""OpenDART 조회 전용 SQLAlchemy repository."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, CompanyDisclosure, CompanyFinancial


class OpenDartRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def company_by_stock_code(self, stock_code: str) -> Company | None:
        return self.session.scalar(select(Company).where(Company.stock_code == stock_code))

    def financials(self, stock_code: str, *, year: str | None, quarter: str | None) -> list[CompanyFinancial]:
        query = select(CompanyFinancial).where(CompanyFinancial.stock_code == stock_code)
        if year:
            query = query.where(CompanyFinancial.business_year == year)
        if quarter:
            query = query.where(CompanyFinancial.quarter == quarter)
        return list(self.session.scalars(query.order_by(CompanyFinancial.business_year.desc(), CompanyFinancial.report_code.desc())))

    def disclosures(
        self,
        stock_code: str,
        *,
        start_date: date | None,
        end_date: date | None,
        disclosure_type: str | None,
        limit: int,
    ) -> list[CompanyDisclosure]:
        query = select(CompanyDisclosure).where(CompanyDisclosure.stock_code == stock_code)
        if start_date:
            query = query.where(CompanyDisclosure.receipt_date >= start_date)
        if end_date:
            query = query.where(CompanyDisclosure.receipt_date <= end_date)
        if disclosure_type:
            query = query.where(CompanyDisclosure.report_name.ilike(f"%{disclosure_type}%"))
        query = query.order_by(CompanyDisclosure.receipt_date.desc(), CompanyDisclosure.receipt_no.desc()).limit(limit)
        return list(self.session.scalars(query))
