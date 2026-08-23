"""내부 가상투자 계좌와 거래 원장을 정의한다."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID as PythonUUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, Numeric, String, Text, func
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


class VirtualAccount(TimestampMixin, Base):
    """KIS 계좌와 무관하게 서비스가 보유하는 사용자별 단일 가상계좌다."""
    __tablename__ = "virtual_accounts"
    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), default=uuid4, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    selected_strategy_id: Mapped[str | None] = mapped_column(String(30), ForeignKey("strategies.id", ondelete="SET NULL"))


class Position(TimestampMixin, Base):
    """체결 결과인 수량·평균매입가와 누적 실현손익만 저장한다."""
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    account_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="CASCADE"), nullable=False)
    stock_code: Mapped[str] = mapped_column(String(12), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    average_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    realized_profit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, server_default="0")


class Order(Base):
    """시장가 주문 요청과 최종 상태를 저장한다."""
    __tablename__ = "orders"
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
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    account_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("virtual_accounts.id", ondelete="RESTRICT"), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
