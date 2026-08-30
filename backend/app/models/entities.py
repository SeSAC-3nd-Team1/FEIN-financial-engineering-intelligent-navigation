"""기존 회원 스키마를 재사용하고 서비스 거래 관계를 매핑한다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "active_operation_mode IN ('AUTO', 'SEMI_AUTO')",
            name="ck_users_active_operation_mode_values",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(16), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(30))
    birthdate: Mapped[str] = mapped_column(String(6))
    phone_number: Mapped[str] = mapped_column(String(11))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    email_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    member_type: Mapped[str] = mapped_column(String(20), default="ASSOCIATE")
    account_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_operation_mode: Mapped[str | None] = mapped_column(String(20))
    operation_mode_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Term(Base):
    __tablename__ = "terms"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    term_code: Mapped[str] = mapped_column(String(30))
    version: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    content_reference: Mapped[str | None] = mapped_column(String(500))
    is_required: Mapped[bool] = mapped_column(Boolean)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserAgreement(Base):
    __tablename__ = "user_agreements"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    term_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("terms.id", ondelete="RESTRICT")
    )
    is_agreed: Mapped[bool] = mapped_column(Boolean)
    agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    agreed_ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(512))


class Strategy(Base):
    __tablename__ = "strategies"
    __table_args__ = (
        CheckConstraint(
            "product_group IN ('MUL', 'BANG')",
            name="ck_strategies_product_group_values",
        ),
        CheckConstraint(
            "availability_status IN ('AVAILABLE', 'TESTING')",
            name="ck_strategies_availability_status_values",
        ),
        CheckConstraint(
            "display_order > 0",
            name="ck_strategies_display_order_positive",
        ),
        Index(
            "ix_strategies_catalog_order",
            "product_group",
            "display_order",
        ),
    )
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(20))
    rebalance_cycle: Mapped[str] = mapped_column(String(30))
    rule_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    product_group: Mapped[str] = mapped_column(String(20))
    availability_status: Mapped[str] = mapped_column(String(20))
    engine_key: Mapped[str] = mapped_column(String(50))
    display_order: Mapped[int] = mapped_column(SmallInteger)


class StrategyTargetWeight(Base):
    __tablename__ = "strategy_target_weights"
    __table_args__ = (
        UniqueConstraint(
            "strategy_id",
            "stock_code",
            "effective_from",
            name="uq_strategy_target_weights_version",
        ),
        CheckConstraint(
            "target_weight >= 0 AND target_weight <= 1",
            name="ck_strategy_target_weights_range",
        ),
        Index(
            "ix_strategy_target_weights_strategy_effective",
            "strategy_id",
            "effective_from",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("strategies.id", ondelete="CASCADE")
    )
    stock_code: Mapped[str] = mapped_column(String(12))
    target_weight: Mapped[Decimal] = mapped_column(Numeric(9, 8))
    effective_from: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VirtualAccount(Base):
    __tablename__ = "virtual_accounts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "operation_mode", name="uq_virtual_accounts_user_mode"
        ),
        CheckConstraint(
            "initial_cash >= 0", name="ck_virtual_accounts_initial_cash_nonnegative"
        ),
        CheckConstraint(
            "invested_principal >= 0",
            name="ck_virtual_accounts_invested_principal_nonnegative",
        ),
        CheckConstraint(
            "operation_mode IN ('AUTO', 'SEMI_AUTO')",
            name="ck_virtual_accounts_operation_mode_values",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    operation_mode: Mapped[str] = mapped_column(String(20))
    account_name: Mapped[str] = mapped_column(String(100))
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    invested_principal: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), default=Decimal("0"), server_default="0"
    )
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    selected_strategy_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("strategies.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InvestmentOnboarding(Base):
    __tablename__ = "investment_onboardings"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "operation_mode", name="uq_investment_onboardings_user_mode"
        ),
        CheckConstraint(
            "investment_amount > 0",
            name="ck_investment_onboardings_investment_amount_positive",
        ),
        CheckConstraint(
            "operation_mode IN ('AUTO', 'SEMI_AUTO')",
            name="ck_investment_onboardings_operation_mode_values",
        ),
        CheckConstraint(
            "status IN ('TERMS_PENDING', 'ACCOUNT_PENDING', 'DEPOSIT_PENDING', 'READY', 'COMPLETED')",
            name="ck_investment_onboardings_status_values",
        ),
        CheckConstraint(
            "(status = 'COMPLETED' AND account_id IS NOT NULL AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND completed_at IS NULL)",
            name="ck_investment_onboardings_completion_consistency",
        ),
        Index("ix_investment_onboardings_status", "status"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    strategy_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("strategies.id", ondelete="RESTRICT")
    )
    investment_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    operation_mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    account_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="RESTRICT")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="CASCADE")
    )
    stock_code: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    average_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    realized_profit: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), default=Decimal("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "snapshot_date", name="uq_portfolio_snapshots_account_date"
        ),
        Index("ix_portfolio_snapshots_account_date", "account_id", "snapshot_date"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="CASCADE")
    )
    snapshot_date: Mapped[date] = mapped_column(Date)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    total_purchase_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    total_evaluation_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    total_assets: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    unrealized_profit: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    realized_profit: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    return_rate: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RebalancingDecision(Base):
    __tablename__ = "rebalancing_decisions"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="uq_rebalancing_decisions_account_idempotency",
        ),
        UniqueConstraint(
            "account_id",
            "proposal_key",
            name="uq_rebalancing_decisions_account_proposal",
        ),
        CheckConstraint(
            "action IN ('BUY', 'SELL')", name="ck_rebalancing_decisions_action_values"
        ),
        CheckConstraint(
            "decision IN ('ACCEPTED', 'HELD')",
            name="ck_rebalancing_decisions_decision_values",
        ),
        Index("ix_rebalancing_decisions_account_created", "account_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="CASCADE")
    )
    strategy_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("strategies.id", ondelete="SET NULL")
    )
    stock_code: Mapped[str] = mapped_column(String(12))
    stock_name: Mapped[str | None] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(4))
    current_weight: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    target_weight: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    weight_diff: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    recommended_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    decision: Mapped[str] = mapped_column(String(10))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    proposal_key: Mapped[str] = mapped_column(String(255))
    baseline_snapshot_date: Mapped[date | None] = mapped_column(Date)
    baseline_total_assets: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="RESTRICT")
    )
    stock_code: Mapped[str] = mapped_column(String(12))
    side: Mapped[str] = mapped_column(String(4))
    order_type: Mapped[str] = mapped_column(String(10), default="MARKET")
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    requested_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    status: Mapped[str] = mapped_column(String(12), default="PENDING")
    idempotency_key: Mapped[str] = mapped_column(String(100))
    rejection_code: Mapped[str | None] = mapped_column(String(50))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MomentumRebalanceRun(Base):
    __tablename__ = "momentum_rebalance_runs"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "execution_year", "execution_quarter",
            name="uq_momentum_rebalance_runs_account_quarter",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="CASCADE")
    )
    execution_year: Mapped[int] = mapped_column(SmallInteger)
    execution_quarter: Mapped[int] = mapped_column(SmallInteger)
    snapshot_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default="RUNNING")
    plan: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Execution(Base):
    __tablename__ = "executions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), unique=True
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="RESTRICT")
    )
    stock_code: Mapped[str] = mapped_column(String(12))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    execution_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CashLedger(Base):
    __tablename__ = "cash_ledger"
    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('INITIAL_DEPOSIT', 'DEPOSIT', "
            "'ADDITIONAL_INVESTMENT', 'WITHDRAWAL', 'BUY', 'SELL', 'ADJUSTMENT')",
            name="ck_cash_ledger_type_values",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="RESTRICT")
    )
    transaction_type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    reference_type: Mapped[str] = mapped_column(String(30))
    reference_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FundOperation(Base):
    """여러 내부 체결을 포함하는 가상 추가투자·출금 작업이다."""

    __tablename__ = "fund_operations"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="uq_fund_operations_account_idempotency",
        ),
        CheckConstraint(
            "operation_type IN ('ADDITIONAL_INVESTMENT', 'WITHDRAWAL')",
            name="ck_fund_operations_operation_type_values",
        ),
        CheckConstraint(
            "status IN ('PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_fund_operations_status_values",
        ),
        CheckConstraint(
            "requested_amount > 0",
            name="ck_fund_operations_requested_amount_positive",
        ),
        CheckConstraint(
            "executed_amount >= 0",
            name="ck_fund_operations_executed_amount_nonnegative",
        ),
        CheckConstraint(
            "principal_before >= 0 AND principal_after >= 0",
            name="ck_fund_operations_principal_nonnegative",
        ),
        CheckConstraint(
            "total_assets_before >= 0 AND total_assets_after >= 0",
            name="ck_fund_operations_total_assets_nonnegative",
        ),
        CheckConstraint(
            "(status = 'COMPLETED' AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED')",
            name="ck_fund_operations_completion_consistency",
        ),
        Index("ix_fund_operations_account_created", "account_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="RESTRICT")
    )
    operation_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    executed_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    principal_before: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    principal_after: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    total_assets_before: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    total_assets_after: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FundOperationOrder(Base):
    """가상 자금 작업과 해당 작업이 만든 주문의 배분 근거다."""

    __tablename__ = "fund_operation_orders"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_fund_operation_orders_order_id"),
        CheckConstraint(
            "allocated_amount > 0",
            name="ck_fund_operation_orders_allocated_amount_positive",
        ),
        CheckConstraint(
            "applied_weight >= 0 AND applied_weight <= 1",
            name="ck_fund_operation_orders_applied_weight_range",
        ),
    )
    fund_operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fund_operations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    applied_weight: Mapped[Decimal] = mapped_column(Numeric(9, 8))


class AccountDeposit(Base):
    """가상계좌 부족분을 정확히 한 번 충전한 결과를 보존한다."""

    __tablename__ = "account_deposits"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="uq_account_deposits_account_idempotency",
        ),
        CheckConstraint("amount > 0", name="ck_account_deposits_amount_positive"),
        CheckConstraint(
            "balance_after >= 0", name="ck_account_deposits_balance_nonnegative"
        ),
        CheckConstraint(
            "status = 'COMPLETED'", name="ck_account_deposits_status_values"
        ),
        Index("ix_account_deposits_account_created", "account_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("virtual_accounts.id", ondelete="RESTRICT"),
    )
    onboarding_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("investment_onboardings.id", ondelete="RESTRICT"),
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    idempotency_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AccountCashDeposit(Base):
    """전략 선택과 무관하게 가상계좌에 충전한 현금 입금 기록."""

    __tablename__ = "account_cash_deposits"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="uq_account_cash_deposits_account_idempotency",
        ),
        CheckConstraint("amount > 0", name="ck_account_cash_deposits_amount_positive"),
        CheckConstraint(
            "balance_after >= 0",
            name="ck_account_cash_deposits_balance_nonnegative",
        ),
        CheckConstraint(
            "status = 'COMPLETED'",
            name="ck_account_cash_deposits_status_values",
        ),
        Index(
            "ix_account_cash_deposits_account_created",
            "account_id",
            "created_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("virtual_accounts.id", ondelete="RESTRICT"),
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    idempotency_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InvestorProfileAssessment(Base):
    __tablename__ = "investor_profile_assessments"
    __table_args__ = (
        CheckConstraint(
            "profile_type IN ('안정추구형', '안정투자형', '중립투자형', '성장추구형', '공격투자형')",
            name="ck_investor_profile_assessments_profile_type_values",
        ),
        CheckConstraint(
            "stability BETWEEN 1 AND 5",
            name="ck_investor_profile_assessments_stability_range",
        ),
        CheckConstraint(
            "return_seeking BETWEEN 1 AND 5",
            name="ck_investor_profile_assessments_return_seeking_range",
        ),
        CheckConstraint(
            "horizon BETWEEN 1 AND 5",
            name="ck_investor_profile_assessments_horizon_range",
        ),
        CheckConstraint(
            "risk_score IS NULL OR risk_score BETWEEN 0 AND 100",
            name="ck_investor_profile_assessments_risk_score_range",
        ),
        Index("ix_investor_profile_assessments_user_created", "user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    questionnaire_version: Mapped[str] = mapped_column(String(20))
    analysis_version: Mapped[str] = mapped_column(String(20))
    risk_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    profile_type: Mapped[str] = mapped_column(String(20))
    stability: Mapped[int] = mapped_column(SmallInteger)
    return_seeking: Mapped[int] = mapped_column(SmallInteger)
    horizon: Mapped[int] = mapped_column(SmallInteger)
    tendency_line: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    analysis_summary: Mapped[list[str]] = mapped_column(JSONB)
    model_version: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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
        Index(
            "ix_strategy_recommendations_assessment_created",
            "assessment_id",
            "created_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    assessment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("investor_profile_assessments.id", ondelete="CASCADE"),
    )
    model_version: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    strategy_catalog_version: Mapped[str] = mapped_column(String(50))
    dataset_version: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StrategyRecommendationItem(Base):
    __tablename__ = "strategy_recommendation_items"
    __table_args__ = (
        UniqueConstraint(
            "recommendation_id", "rank", name="uq_strategy_recommendation_items_rank"
        ),
        CheckConstraint(
            "rank BETWEEN 1 AND 3", name="ck_strategy_recommendation_items_rank_range"
        ),
        CheckConstraint(
            "score >= 0 AND score <= 1",
            name="ck_strategy_recommendation_items_score_range",
        ),
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CompanyFinancial(Base):
    __tablename__ = "company_financials"
    __table_args__ = (
        UniqueConstraint("corp_code", "business_year", "report_code", "fs_div"),
    )
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StockDividend(Base):
    __tablename__ = "stock_dividends"
    __table_args__ = (
        UniqueConstraint(
            "stock_code",
            "business_year",
            "report_code",
            "stock_kind",
            name="uq_stock_dividends_report_kind",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(12))
    corp_code: Mapped[str] = mapped_column(String(8), ForeignKey("companies.corp_code"))
    business_year: Mapped[str] = mapped_column(String(4))
    report_code: Mapped[str] = mapped_column(String(5))
    stock_kind: Mapped[str] = mapped_column(String(20))
    raw_stock_kind: Mapped[str | None] = mapped_column(String(100))
    dividend_per_share: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    reported_dividend_yield: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    total_dividend: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    dividend_payout_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    receipt_no: Mapped[str | None] = mapped_column(String(20))
    settlement_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(30))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
