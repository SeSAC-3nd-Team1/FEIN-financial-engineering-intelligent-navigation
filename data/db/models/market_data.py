"""Frontend 조회를 위한 KRX 서비스 데이터 모델이다."""

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Identity, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models.common import TimestampMixin


class MarketStock(TimestampMixin, Base):
    """KRX 종목기본정보의 최신 상태다."""

    __tablename__ = "market_stocks"
    __table_args__ = (
        CheckConstraint("market IN ('KOSPI', 'KOSDAQ')", name="market_values"),
        Index("ix_market_stocks_market", "market"),
    )
    stock_code: Mapped[str] = mapped_column(String(6), primary_key=True)
    isin_code: Mapped[str | None] = mapped_column(String(20), unique=True)
    stock_name: Mapped[str] = mapped_column(String(200), nullable=False)
    stock_name_full: Mapped[str | None] = mapped_column(String(300))
    stock_name_eng: Mapped[str | None] = mapped_column(String(300))
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    listing_date: Mapped[date | None] = mapped_column(Date)
    listed_shares: Mapped[int | None] = mapped_column(BigInteger)
    security_type: Mapped[str | None] = mapped_column(String(100))
    sector: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)


class MarketStockPrice(TimestampMixin, Base):
    """종목·거래일별 KRX OHLCV와 시가총액이다."""

    __tablename__ = "market_stock_prices"
    __table_args__ = (
        UniqueConstraint("stock_code", "trade_date", name="uq_market_stock_prices_code_date"),
        Index("ix_market_stock_prices_code_date", "stock_code", "trade_date"),
        Index("ix_market_stock_prices_date", "trade_date"),
        CheckConstraint("volume >= 0", name="volume_nonnegative"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    stock_code: Mapped[str] = mapped_column(
        String(6), ForeignKey("market_stocks.stock_code", ondelete="RESTRICT"), nullable=False
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    high_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    low_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    change_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    change_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    trading_value: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    listed_shares: Mapped[int | None] = mapped_column(BigInteger)
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)


class MarketIndex(TimestampMixin, Base):
    """시장 지수·거래일별 KRX OHLCV다."""

    __tablename__ = "market_indices"
    __table_args__ = (
        UniqueConstraint("index_code", "trade_date", name="uq_market_indices_code_date"),
        Index("ix_market_indices_name_date", "index_name", "trade_date"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    index_code: Mapped[str] = mapped_column(String(300), nullable=False)
    index_name: Mapped[str] = mapped_column(String(200), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    high_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    low_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    close_value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    change_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    change_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    trading_value: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(30, 2))
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
