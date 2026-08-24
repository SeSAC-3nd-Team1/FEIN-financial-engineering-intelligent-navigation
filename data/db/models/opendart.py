"""OpenDART 기업·재무·공시 정제 데이터를 저장하는 ORM 모델이다."""

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Identity, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models.common import TimestampMixin


class Company(TimestampMixin, Base):
    """DART 고유번호와 거래소 종목코드의 기업 마스터다."""

    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_stock_code", "stock_code"),
        Index("ix_companies_corp_name", "corp_name"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    corp_code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    stock_code: Mapped[str | None] = mapped_column(String(12))
    corp_name: Mapped[str] = mapped_column(String(200), nullable=False)
    corp_name_eng: Mapped[str | None] = mapped_column(String(200))
    stock_name: Mapped[str | None] = mapped_column(String(200))
    market: Mapped[str | None] = mapped_column(String(10))
    ceo_name: Mapped[str | None] = mapped_column(String(200))
    jurir_no: Mapped[str | None] = mapped_column(String(20))
    bizr_no: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    ir_url: Mapped[str | None] = mapped_column(Text)
    phone_number: Mapped[str | None] = mapped_column(String(100))
    industry_code: Mapped[str | None] = mapped_column(String(20))
    established_date: Mapped[date | None] = mapped_column(Date)
    accounting_month: Mapped[str | None] = mapped_column(String(2))
    dart_modify_date: Mapped[date | None] = mapped_column(Date)


class CompanyFinancialAccount(TimestampMixin, Base):
    """OpenDART 재무제표의 계정별 원본 정제 행이다."""

    __tablename__ = "company_financial_accounts"
    __table_args__ = (
        UniqueConstraint(
            "corp_code", "business_year", "report_code", "fs_div", "sj_div", "account_id",
            name="uq_financial_accounts_identity",
        ),
        Index("ix_financial_accounts_stock_year", "stock_code", "business_year"),
        Index("ix_financial_accounts_corp_year", "corp_code", "business_year"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    corp_code: Mapped[str] = mapped_column(String(8), ForeignKey("companies.corp_code", ondelete="RESTRICT"), nullable=False)
    stock_code: Mapped[str | None] = mapped_column(String(12))
    business_year: Mapped[str] = mapped_column(String(4), nullable=False)
    report_code: Mapped[str] = mapped_column(String(5), nullable=False)
    fs_div: Mapped[str] = mapped_column(String(10), nullable=False)
    sj_div: Mapped[str] = mapped_column(String(10), nullable=False)
    account_id: Mapped[str] = mapped_column(String(200), nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    current_amount: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    previous_amount: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    currency: Mapped[str] = mapped_column(String(10), nullable=False, server_default="KRW")


class CompanyFinancial(TimestampMixin, Base):
    """서비스 조회에 필요한 핵심 재무지표를 보고서 단위로 집계한다."""

    __tablename__ = "company_financials"
    __table_args__ = (
        UniqueConstraint("corp_code", "business_year", "report_code", "fs_div", name="uq_company_financials_report"),
        Index("ix_company_financials_stock_year", "stock_code", "business_year"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    corp_code: Mapped[str] = mapped_column(String(8), ForeignKey("companies.corp_code", ondelete="RESTRICT"), nullable=False)
    stock_code: Mapped[str | None] = mapped_column(String(12))
    business_year: Mapped[str] = mapped_column(String(4), nullable=False)
    report_code: Mapped[str] = mapped_column(String(5), nullable=False)
    quarter: Mapped[str] = mapped_column(String(10), nullable=False)
    fs_div: Mapped[str] = mapped_column(String(10), nullable=False)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    operating_income: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    net_income: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    total_assets: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    total_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    total_equity: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    operating_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    investing_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    financing_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))


class CompanyDisclosure(TimestampMixin, Base):
    """접수번호로 중복을 막는 OpenDART 공시 목록이다."""

    __tablename__ = "company_disclosures"
    __table_args__ = (
        Index("ix_company_disclosures_corp_code", "corp_code"),
        Index("ix_company_disclosures_stock_code", "stock_code"),
        Index("ix_company_disclosures_receipt_date", "receipt_date"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    receipt_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    corp_code: Mapped[str] = mapped_column(String(8), ForeignKey("companies.corp_code", ondelete="RESTRICT"), nullable=False)
    stock_code: Mapped[str | None] = mapped_column(String(12))
    corp_name: Mapped[str] = mapped_column(String(200), nullable=False)
    report_name: Mapped[str] = mapped_column(String(500), nullable=False)
    filer_name: Mapped[str | None] = mapped_column(String(200))
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)
