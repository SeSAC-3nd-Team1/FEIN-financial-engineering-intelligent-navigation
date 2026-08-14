"""Market index and macroeconomic time series."""

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    Identity,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models.common import TimestampMixin
from db.models.stock import RAW_SCHEMA


class MarketIndexDaily(TimestampMixin, Base):
    """Daily OHLC and return for KOSPI/KOSDAQ/KOSPI200 and future indices."""

    __tablename__ = "market_index_daily"
    __table_args__ = (
        UniqueConstraint(
            "index_code", "trade_date", name="uq_market_index_daily_code_date"
        ),
        Index("ix_market_index_daily_code_date", "index_code", "trade_date"),
        Index("ix_market_index_daily_date_code", "trade_date", "index_code"),
        {"schema": RAW_SCHEMA},
    )

    market_index_id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    index_code: Mapped[str] = mapped_column(String(100), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    high_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    low_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    close_value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    change_rate: Mapped[Decimal | None] = mapped_column(Numeric(16, 10))
    source: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("'KRX_INDEX'")
    )
    source_payload: Mapped[dict | None] = mapped_column(JSONB)


class MacroIndicator(TimestampMixin, Base):
    """ECOS observations such as the policy rate, USD/KRW, and CPI."""

    __tablename__ = "macro_indicator"
    __table_args__ = (
        UniqueConstraint(
            "indicator_code",
            "observation_date",
            "frequency",
            name="uq_macro_indicator_code_date_frequency",
        ),
        Index(
            "ix_macro_indicator_code_date", "indicator_code", "observation_date"
        ),
        Index(
            "ix_macro_indicator_date_code", "observation_date", "indicator_code"
        ),
        {"schema": RAW_SCHEMA},
    )

    macro_indicator_id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    indicator_code: Mapped[str] = mapped_column(String(100), nullable=False)
    indicator_name: Mapped[str | None] = mapped_column(String(200))
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    frequency: Mapped[str] = mapped_column(String(10), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("'BOK_ECOS'")
    )
    source_payload: Mapped[dict | None] = mapped_column(JSONB)
