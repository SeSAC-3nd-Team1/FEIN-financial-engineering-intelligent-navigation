"""기존 회원 스키마를 재사용하고 서비스 거래 관계를 매핑한다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, String, Text, func
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
