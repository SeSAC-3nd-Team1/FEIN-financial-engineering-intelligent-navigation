"""add KRX market serving tables

Revision ID: 20260824_0016
Revises: 20260824_0015
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_0016"
down_revision: str | None = "20260824_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Blob 분석 계층과 분리된 최소 서비스 조회 테이블을 생성한다."""

    op.create_table(
        "market_stocks",
        sa.Column("stock_code", sa.String(6), primary_key=True),
        sa.Column("isin_code", sa.String(20), unique=True),
        sa.Column("stock_name", sa.String(200), nullable=False),
        sa.Column("stock_name_full", sa.String(300)),
        sa.Column("stock_name_eng", sa.String(300)),
        sa.Column("market", sa.String(10), nullable=False),
        sa.Column("listing_date", sa.Date()),
        sa.Column("listed_shares", sa.BigInteger()),
        sa.Column("security_type", sa.String(100)),
        sa.Column("sector", sa.String(100)),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("market IN ('KOSPI', 'KOSDAQ')", name="ck_market_stocks_market_values"),
    )
    op.create_index("ix_market_stocks_market", "market_stocks", ["market"])

    op.create_table(
        "market_stock_prices",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("stock_code", sa.String(6), sa.ForeignKey("market_stocks.stock_code", ondelete="RESTRICT"), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("high_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("low_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("close_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("change_amount", sa.Numeric(20, 4)),
        sa.Column("change_rate", sa.Numeric(12, 6)),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("trading_value", sa.Numeric(30, 2)),
        sa.Column("market_cap", sa.Numeric(30, 2)),
        sa.Column("listed_shares", sa.BigInteger()),
        sa.Column("market", sa.String(10), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("stock_code", "trade_date", name="uq_market_stock_prices_code_date"),
        sa.CheckConstraint("volume >= 0", name="ck_market_stock_prices_volume_nonnegative"),
    )
    op.create_index("ix_market_stock_prices_code_date", "market_stock_prices", ["stock_code", "trade_date"])
    op.create_index("ix_market_stock_prices_date", "market_stock_prices", ["trade_date"])

    op.create_table(
        "market_indices",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("index_code", sa.String(300), nullable=False),
        sa.Column("index_name", sa.String(200), nullable=False),
        sa.Column("market", sa.String(10), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open_value", sa.Numeric(20, 6)),
        sa.Column("high_value", sa.Numeric(20, 6)),
        sa.Column("low_value", sa.Numeric(20, 6)),
        sa.Column("close_value", sa.Numeric(20, 6), nullable=False),
        sa.Column("change_amount", sa.Numeric(20, 6)),
        sa.Column("change_rate", sa.Numeric(12, 6)),
        sa.Column("volume", sa.BigInteger()),
        sa.Column("trading_value", sa.Numeric(30, 2)),
        sa.Column("market_cap", sa.Numeric(30, 2)),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("index_code", "trade_date", name="uq_market_indices_code_date"),
    )
    op.create_index("ix_market_indices_name_date", "market_indices", ["index_name", "trade_date"])


def downgrade() -> None:
    op.drop_table("market_indices")
    op.drop_table("market_stock_prices")
    op.drop_table("market_stocks")

