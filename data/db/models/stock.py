"""Stock master, prices, issuance, and point-in-time financial statements."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from db.models.common import TimestampMixin


RAW_SCHEMA = "raw"


class StockMaster(TimestampMixin, Base):
    """Latest normalized KRX listing master row for one stock code."""

    __tablename__ = "stock_master"
    __table_args__ = (
        UniqueConstraint("stock_code", name="uq_stock_master_stock_code"),
        UniqueConstraint("isin", name="uq_stock_master_isin"),
        Index("ix_stock_master_market_code", "market_type", "stock_code"),
        Index("ix_stock_master_reference_date", "reference_date"),
        {"schema": RAW_SCHEMA},
    )

    stock_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    # KRX short codes include domestic six-digit values and prefixed foreign codes.
    stock_code: Mapped[str] = mapped_column(String(12), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(12))
    market_type: Mapped[str] = mapped_column(String(20), nullable=False)
    stock_name: Mapped[str] = mapped_column(String(200), nullable=False)
    corporation_registration_number: Mapped[str | None] = mapped_column(String(20))
    corporation_name: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("'FSC_KRX_LISTED_STOCK'")
    )
    source_payload: Mapped[dict | None] = mapped_column(JSONB)

    prices: Mapped[list[StockPriceDaily]] = relationship(back_populates="stock")
    issuances: Mapped[list[StockIssuance]] = relationship(back_populates="stock")
    financial_statements: Mapped[list[FinancialStatement]] = relationship(
        back_populates="stock"
    )


class StockPriceDaily(TimestampMixin, Base):
    """Daily OHLCV, retaining whether prices are raw or adjusted."""

    __tablename__ = "stock_price_daily"
    __table_args__ = (
        UniqueConstraint(
            "stock_id",
            "trade_date",
            "price_type",
            name="uq_stock_price_daily_stock_date_type",
        ),
        CheckConstraint(
            "price_type IN ('unadjusted', 'adjusted')",
            name="price_type_valid",
        ),
        CheckConstraint("volume >= 0", name="volume_nonnegative"),
        Index("ix_stock_price_daily_stock_date", "stock_id", "trade_date"),
        Index("ix_stock_price_daily_date_stock", "trade_date", "stock_id"),
        {"schema": RAW_SCHEMA},
    )

    price_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("raw.stock_master.stock_id", ondelete="RESTRICT"), nullable=False
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'unadjusted'")
    )
    open_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    high_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    low_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    close_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    trading_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    adjustment_factor: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'KRW'")
    )
    source: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("'FSC_STOCK_PRICE'")
    )
    source_payload: Mapped[dict | None] = mapped_column(JSONB)

    stock: Mapped[StockMaster] = relationship(back_populates="prices")


class StockIssuance(TimestampMixin, Base):
    """Point-in-time stock issuance and listing information."""

    __tablename__ = "stock_issuance"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "reference_date", name="uq_stock_issuance_stock_date"
        ),
        CheckConstraint("issued_shares >= 0", name="issued_shares_nonnegative"),
        Index("ix_stock_issuance_stock_date", "stock_id", "reference_date"),
        Index("ix_stock_issuance_date_stock", "reference_date", "stock_id"),
        {"schema": RAW_SCHEMA},
    )

    issuance_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("raw.stock_master.stock_id", ondelete="RESTRICT"), nullable=False
    )
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    issued_shares: Mapped[int | None] = mapped_column(BigInteger)
    par_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    listing_date: Mapped[date | None] = mapped_column(Date)
    delisting_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("'FSC_STOCK_ISSUANCE'")
    )
    source_payload: Mapped[dict | None] = mapped_column(JSONB)

    stock: Mapped[StockMaster] = relationship(back_populates="issuances")


class FinancialStatement(TimestampMixin, Base):
    """OpenDART statement with explicit point-in-time availability semantics."""

    __tablename__ = "financial_statement"
    __table_args__ = (
        UniqueConstraint(
            "corp_code",
            "business_year",
            "report_code",
            "fiscal_period",
            "statement_scope",
            name="uq_financial_statement_period_scope",
        ),
        CheckConstraint(
            "available_date >= report_date", name="available_date_after_report_date"
        ),
        Index(
            "ix_financial_statement_stock_available",
            "stock_id",
            "available_date",
        ),
        Index(
            "ix_financial_statement_available_stock",
            "available_date",
            "stock_id",
        ),
        Index(
            "ix_financial_statement_corp_period",
            "corp_code",
            "business_year",
            "report_code",
        ),
        {"schema": RAW_SCHEMA},
    )

    financial_statement_id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    stock_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw.stock_master.stock_id", ondelete="RESTRICT")
    )
    corp_code: Mapped[str] = mapped_column(String(8), nullable=False)
    receipt_number: Mapped[str | None] = mapped_column(String(20), unique=True)
    business_year: Mapped[str] = mapped_column(String(4), nullable=False)
    report_code: Mapped[str] = mapped_column(String(5), nullable=False)
    fiscal_period: Mapped[str] = mapped_column(String(20), nullable=False)
    statement_scope: Mapped[str] = mapped_column(String(3), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    disclosure_date: Mapped[date] = mapped_column(Date, nullable=False)
    available_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'KRW'")
    )
    assets: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    current_assets: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    liabilities: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    equity: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    operating_income: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    net_income: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    interest_expense: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    account_data: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("'OPENDART'")
    )
    source_payload: Mapped[dict | None] = mapped_column(JSONB)

    stock: Mapped[StockMaster | None] = relationship(
        back_populates="financial_statements"
    )
