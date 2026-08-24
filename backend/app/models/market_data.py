"""KRX 서비스 조회 테이블의 Backend ORM mapping."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketStock(Base):
    __tablename__ = "market_stocks"
    stock_code: Mapped[str] = mapped_column(String(6), primary_key=True)
    isin_code: Mapped[str | None] = mapped_column(String(20))
    stock_name: Mapped[str] = mapped_column(String(200))
    stock_name_full: Mapped[str | None] = mapped_column(String(300))
    stock_name_eng: Mapped[str | None] = mapped_column(String(300))
    market: Mapped[str] = mapped_column(String(10))
    listing_date: Mapped[date | None] = mapped_column(Date)
    listed_shares: Mapped[int | None] = mapped_column(BigInteger)
    security_type: Mapped[str | None] = mapped_column(String(100))
    sector: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(20))
    as_of: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketStockPrice(Base):
    __tablename__ = "market_stock_prices"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(6), ForeignKey("market_stocks.stock_code"))
    trade_date: Mapped[date] = mapped_column(Date)
    open_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    high_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    low_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    close_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    change_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    change_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    volume: Mapped[int] = mapped_column(BigInteger)
    trading_value: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    listed_shares: Mapped[int | None] = mapped_column(BigInteger)
    market: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(20))
    as_of: Mapped[date] = mapped_column(Date)

