"""기존 회원 스키마를 재사용하고 서비스 거래 관계를 매핑한다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(16), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(30))
    birthdate: Mapped[str] = mapped_column(String(6))
    phone_number: Mapped[str] = mapped_column(String(11))
    phone_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    email_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    member_type: Mapped[str] = mapped_column(String(20), default="ASSOCIATE")
    account_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Term(Base):
    __tablename__ = "terms"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    term_code: Mapped[str] = mapped_column(String(30))
    version: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    is_required: Mapped[bool] = mapped_column(Boolean)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserAgreement(Base):
    __tablename__ = "user_agreements"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"))
    term_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("terms.id", ondelete="RESTRICT"))
    is_agreed: Mapped[bool] = mapped_column(Boolean)
    agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Strategy(Base):
    __tablename__ = "strategies"
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(20))
    rebalance_cycle: Mapped[str] = mapped_column(String(30))
    rule_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class VirtualAccount(Base):
    __tablename__ = "virtual_accounts"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), unique=True)
    account_name: Mapped[str] = mapped_column(String(100))
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    selected_strategy_id: Mapped[str | None] = mapped_column(String(30), ForeignKey("strategies.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="CASCADE"))
    stock_code: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[int] = mapped_column(BigInteger)
    average_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    realized_profit: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="RESTRICT"))
    stock_code: Mapped[str] = mapped_column(String(12))
    side: Mapped[str] = mapped_column(String(4))
    order_type: Mapped[str] = mapped_column(String(10), default="MARKET")
    quantity: Mapped[int] = mapped_column(BigInteger)
    requested_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    status: Mapped[str] = mapped_column(String(12), default="PENDING")
    idempotency_key: Mapped[str] = mapped_column(String(100))
    rejection_code: Mapped[str | None] = mapped_column(String(50))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Execution(Base):
    __tablename__ = "executions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), unique=True)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="RESTRICT"))
    stock_code: Mapped[str] = mapped_column(String(12))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[int] = mapped_column(BigInteger)
    execution_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CashLedger(Base):
    __tablename__ = "cash_ledger"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="RESTRICT"))
    transaction_type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    reference_type: Mapped[str] = mapped_column(String(30))
    reference_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvestorProfileAssessment(Base):
    __tablename__ = "investor_profile_assessments"
    __table_args__ = (
        CheckConstraint(
            "profile_type IN ('안정추구형', '안정투자형', '중립투자형', '성장추구형', '공격투자형')",
            name="ck_investor_profile_assessments_profile_type_values",
        ),
        CheckConstraint("stability BETWEEN 1 AND 5", name="ck_investor_profile_assessments_stability_range"),
        CheckConstraint("return_seeking BETWEEN 1 AND 5", name="ck_investor_profile_assessments_return_seeking_range"),
        CheckConstraint("horizon BETWEEN 1 AND 5", name="ck_investor_profile_assessments_horizon_range"),
        Index("ix_investor_profile_assessments_user_created", "user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"))
    questionnaire_version: Mapped[str] = mapped_column(String(20))
    analysis_version: Mapped[str] = mapped_column(String(20))
    profile_type: Mapped[str] = mapped_column(String(20))
    stability: Mapped[int] = mapped_column(SmallInteger)
    return_seeking: Mapped[int] = mapped_column(SmallInteger)
    horizon: Mapped[int] = mapped_column(SmallInteger)
    tendency_line: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    analysis_summary: Mapped[list[str]] = mapped_column(JSONB)
    model_version: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StrategyRecommendation(Base):
    __tablename__ = "strategy_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "model_version",
            "prompt_version",
            "strategy_catalog_version",
            "dataset_version",
            name="uq_strategy_recommendations_reproducible_input",
        ),
        Index("ix_strategy_recommendations_assessment_created", "assessment_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    assessment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("investor_profile_assessments.id", ondelete="CASCADE"),
    )
    model_version: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    strategy_catalog_version: Mapped[str] = mapped_column(String(50))
    dataset_version: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StrategyRecommendationItem(Base):
    __tablename__ = "strategy_recommendation_items"
    __table_args__ = (
        UniqueConstraint("recommendation_id", "rank", name="uq_strategy_recommendation_items_rank"),
        CheckConstraint("rank BETWEEN 1 AND 3", name="ck_strategy_recommendation_items_rank_range"),
        CheckConstraint("score >= 0 AND score <= 1", name="ck_strategy_recommendation_items_score_range"),
        CheckConstraint(
            "match_level IN ('BEST', 'GOOD', 'CAUTION')",
            name="ck_strategy_recommendation_items_match_level_values",
        ),
    )
    recommendation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_recommendations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    strategy_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("strategies.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    rank: Mapped[int] = mapped_column(SmallInteger)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    match_level: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(Text)
    caution: Mapped[str] = mapped_column(Text)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    corp_code: Mapped[str] = mapped_column(String(8), unique=True)
    stock_code: Mapped[str | None] = mapped_column(String(12), index=True)
    corp_name: Mapped[str] = mapped_column(String(200))
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
    established_date: Mapped[date | None]
    accounting_month: Mapped[str | None] = mapped_column(String(2))
    dart_modify_date: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanyFinancial(Base):
    __tablename__ = "company_financials"
    __table_args__ = (UniqueConstraint("corp_code", "business_year", "report_code", "fs_div"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    corp_code: Mapped[str] = mapped_column(String(8), ForeignKey("companies.corp_code"))
    stock_code: Mapped[str | None] = mapped_column(String(12))
    business_year: Mapped[str] = mapped_column(String(4))
    report_code: Mapped[str] = mapped_column(String(5))
    quarter: Mapped[str] = mapped_column(String(10))
    fs_div: Mapped[str] = mapped_column(String(10))
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    operating_income: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    net_income: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    total_assets: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    total_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    total_equity: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    operating_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    investing_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    financing_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanyDisclosure(Base):
    __tablename__ = "company_disclosures"
    __table_args__ = (
        Index("ix_company_disclosures_corp_code", "corp_code"),
        Index("ix_company_disclosures_receipt_date", "receipt_date"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    receipt_no: Mapped[str] = mapped_column(String(20), unique=True)
    corp_code: Mapped[str] = mapped_column(String(8), ForeignKey("companies.corp_code"))
    stock_code: Mapped[str | None] = mapped_column(String(12), index=True)
    corp_name: Mapped[str] = mapped_column(String(200))
    report_name: Mapped[str] = mapped_column(String(500))
    filer_name: Mapped[str | None] = mapped_column(String(200))
    receipt_date: Mapped[date]
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
