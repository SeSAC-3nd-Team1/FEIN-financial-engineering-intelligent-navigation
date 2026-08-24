"""내부 가상투자 계좌와 거래 원장을 정의한다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID as PythonUUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Identity, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models.common import TimestampMixin


class Strategy(Base):
    """모델 구현과 분리된 서비스용 전략 catalog다."""
    __tablename__ = "strategies"
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    rebalance_cycle: Mapped[str] = mapped_column(String(30), nullable=False)
    rule_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)


class StrategyTargetWeight(Base):
    """전략이 명시적으로 산출한 종목별 목표 비중의 유효일 버전이다."""

    __tablename__ = "strategy_target_weights"
    __table_args__ = (
        UniqueConstraint("strategy_id", "stock_code", "effective_from", name="uq_strategy_target_weights_version"),
        CheckConstraint("target_weight >= 0 AND target_weight <= 1", name="target_weight_range"),
        Index("ix_strategy_target_weights_strategy_effective", "strategy_id", "effective_from"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(30), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False)
    stock_code: Mapped[str] = mapped_column(String(12), nullable=False)
    target_weight: Mapped[Decimal] = mapped_column(Numeric(9, 8), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class VirtualAccount(TimestampMixin, Base):
    """KIS 계좌와 무관하게 서비스가 보유하는 사용자별 단일 가상계좌다."""
    __tablename__ = "virtual_accounts"
    __table_args__ = (Index("ix_virtual_accounts_status", "status"),)
    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), default=uuid4, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    selected_strategy_id: Mapped[str | None] = mapped_column(String(30), ForeignKey("strategies.id", ondelete="SET NULL"))


class InvestmentOnboarding(TimestampMixin, Base):
    """투자 약관 확인부터 가상계좌 준비까지의 서버 기준 진행 상태다."""

    __tablename__ = "investment_onboardings"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_investment_onboardings_user_id"),
        CheckConstraint("investment_amount > 0", name="investment_amount_positive"),
        CheckConstraint(
            "operation_mode IN ('AUTO', 'SEMI_AUTO')",
            name="operation_mode_values",
        ),
        CheckConstraint(
            "status IN ('TERMS_PENDING', 'ACCOUNT_PENDING', 'READY', 'COMPLETED')",
            name="status_values",
        ),
        CheckConstraint(
            "(status = 'COMPLETED' AND account_id IS NOT NULL AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND completed_at IS NULL)",
            name="completion_consistency",
        ),
        Index("ix_investment_onboardings_status", "status"),
    )
    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), default=uuid4, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    strategy_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("strategies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    investment_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    operation_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    account_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("virtual_accounts.id", ondelete="RESTRICT"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Position(TimestampMixin, Base):
    """체결 결과인 수량·평균매입가와 누적 실현손익만 저장한다."""
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("account_id", "stock_code", name="uq_positions_account_stock"),
        Index("ix_positions_account_id", "account_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    account_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="CASCADE"), nullable=False)
    stock_code: Mapped[str] = mapped_column(String(12), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    average_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    realized_profit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, server_default="0")


class PortfolioSnapshot(TimestampMixin, Base):
    """조회 시점의 실제 계좌 평가를 계좌·일자별 한 건으로 보존한다."""

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "snapshot_date", name="uq_portfolio_snapshots_account_date"),
        Index("ix_portfolio_snapshots_account_date", "account_id", "snapshot_date"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    account_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="CASCADE"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    total_purchase_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    total_evaluation_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    total_assets: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    unrealized_profit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    realized_profit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    return_rate: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)


class RebalancingDecision(Base):
    """서버가 산출한 리밸런싱 제안과 사용자의 선택을 변경 불가능한 사실로 보존한다."""

    __tablename__ = "rebalancing_decisions"
    __table_args__ = (
        UniqueConstraint("account_id", "idempotency_key", name="uq_rebalancing_decisions_account_idempotency"),
        CheckConstraint("action IN ('BUY', 'SELL')", name="action_values"),
        CheckConstraint("decision IN ('ACCEPTED', 'HELD')", name="decision_values"),
        Index("ix_rebalancing_decisions_account_created", "account_id", "created_at"),
    )
    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), default=uuid4, primary_key=True)
    account_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="CASCADE"), nullable=False)
    strategy_id: Mapped[str | None] = mapped_column(String(30), ForeignKey("strategies.id", ondelete="SET NULL"))
    stock_code: Mapped[str] = mapped_column(String(12), nullable=False)
    stock_name: Mapped[str | None] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(4), nullable=False)
    current_weight: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)
    target_weight: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)
    weight_diff: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)
    recommended_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    baseline_snapshot_date: Mapped[date | None] = mapped_column(Date)
    baseline_total_assets: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Order(Base):
    """시장가 주문 요청과 최종 상태를 저장한다."""
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("account_id", "idempotency_key", name="uq_orders_account_idempotency"),
        Index("ix_orders_account_requested_at", "account_id", "requested_at"),
    )
    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), default=uuid4, primary_key=True)
    account_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="RESTRICT"), nullable=False)
    stock_code: Mapped[str] = mapped_column(String(12), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    order_type: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requested_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    rejection_code: Mapped[str | None] = mapped_column(String(50))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Execution(Base):
    """내부 가상 거래 엔진이 만든 체결 사실이다."""
    __tablename__ = "executions"
    __table_args__ = (Index("ix_executions_account_executed_at", "account_id", "executed_at"),)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), unique=True, nullable=False)
    account_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="RESTRICT"), nullable=False)
    stock_code: Mapped[str] = mapped_column(String(12), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    execution_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CashLedger(Base):
    """현재 잔액의 모든 증감 사유를 보존하는 append-only 원장이다."""
    __tablename__ = "cash_ledger"
    __table_args__ = (
        Index("ix_cash_ledger_account_created_at", "account_id", "created_at"),
        Index("ix_cash_ledger_reference", "reference_type", "reference_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    account_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="RESTRICT"), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
