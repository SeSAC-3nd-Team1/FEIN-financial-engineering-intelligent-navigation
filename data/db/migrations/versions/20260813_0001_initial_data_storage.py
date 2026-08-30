"""create raw and processed data storage

Revision ID: 20260813_0001
Revises:
Create Date: 2026-08-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260813_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS raw")
    op.execute("CREATE SCHEMA IF NOT EXISTS processed")

    op.create_table(
        "stock_master",
        sa.Column("stock_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("stock_code", sa.String(length=6), nullable=False),
        sa.Column("isin", sa.String(length=12), nullable=True),
        sa.Column("market_type", sa.String(length=20), nullable=False),
        sa.Column("stock_name", sa.String(length=200), nullable=False),
        sa.Column("corporation_registration_number", sa.String(length=20)),
        sa.Column("corporation_name", sa.String(length=200)),
        sa.Column(
            "source",
            sa.String(length=100),
            server_default=sa.text("'FSC_KRX_LISTED_STOCK'"),
            nullable=False,
        ),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text())),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("stock_id", name="pk_stock_master"),
        sa.UniqueConstraint("isin", name="uq_stock_master_isin"),
        sa.UniqueConstraint("stock_code", name="uq_stock_master_stock_code"),
        schema="raw",
    )
    op.create_index(
        "ix_stock_master_market_code",
        "stock_master",
        ["market_type", "stock_code"],
        schema="raw",
    )
    op.create_index(
        "ix_stock_master_reference_date",
        "stock_master",
        ["reference_date"],
        schema="raw",
    )

    op.create_table(
        "stock_price_daily",
        sa.Column("price_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("stock_id", sa.BigInteger(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column(
            "price_type",
            sa.String(length=16),
            server_default=sa.text("'unadjusted'"),
            nullable=False,
        ),
        sa.Column("open_price", sa.Numeric(20, 4)),
        sa.Column("high_price", sa.Numeric(20, 4)),
        sa.Column("low_price", sa.Numeric(20, 4)),
        sa.Column("close_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("volume", sa.BigInteger()),
        sa.Column("trading_value", sa.Numeric(28, 2)),
        sa.Column("adjustment_factor", sa.Numeric(20, 10)),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'KRW'"),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.String(length=100),
            server_default=sa.text("'FSC_STOCK_PRICE'"),
            nullable=False,
        ),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text())),
        *timestamp_columns(),
        sa.CheckConstraint(
            "price_type IN ('unadjusted', 'adjusted')",
            name="ck_stock_price_daily_price_type_valid",
        ),
        sa.CheckConstraint(
            "volume >= 0", name="ck_stock_price_daily_volume_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["raw.stock_master.stock_id"],
            name="fk_stock_price_daily_stock_id_stock_master",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("price_id", name="pk_stock_price_daily"),
        sa.UniqueConstraint(
            "stock_id",
            "trade_date",
            "price_type",
            name="uq_stock_price_daily_stock_date_type",
        ),
        schema="raw",
    )
    op.create_index(
        "ix_stock_price_daily_stock_date",
        "stock_price_daily",
        ["stock_id", "trade_date"],
        schema="raw",
    )
    op.create_index(
        "ix_stock_price_daily_date_stock",
        "stock_price_daily",
        ["trade_date", "stock_id"],
        schema="raw",
    )

    op.create_table(
        "market_index_daily",
        sa.Column("market_index_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("index_code", sa.String(length=30), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open_value", sa.Numeric(20, 6)),
        sa.Column("high_value", sa.Numeric(20, 6)),
        sa.Column("low_value", sa.Numeric(20, 6)),
        sa.Column("close_value", sa.Numeric(20, 6), nullable=False),
        sa.Column("change_rate", sa.Numeric(16, 10)),
        sa.Column(
            "source",
            sa.String(length=100),
            server_default=sa.text("'KRX_INDEX'"),
            nullable=False,
        ),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text())),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("market_index_id", name="pk_market_index_daily"),
        sa.UniqueConstraint(
            "index_code", "trade_date", name="uq_market_index_daily_code_date"
        ),
        schema="raw",
    )
    op.create_index(
        "ix_market_index_daily_code_date",
        "market_index_daily",
        ["index_code", "trade_date"],
        schema="raw",
    )
    op.create_index(
        "ix_market_index_daily_date_code",
        "market_index_daily",
        ["trade_date", "index_code"],
        schema="raw",
    )

    op.create_table(
        "stock_issuance",
        sa.Column("issuance_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("stock_id", sa.BigInteger(), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("issued_shares", sa.BigInteger()),
        sa.Column("par_value", sa.Numeric(20, 4)),
        sa.Column("listing_date", sa.Date()),
        sa.Column("delisting_date", sa.Date()),
        sa.Column(
            "source",
            sa.String(length=100),
            server_default=sa.text("'FSC_STOCK_ISSUANCE'"),
            nullable=False,
        ),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text())),
        *timestamp_columns(),
        sa.CheckConstraint(
            "issued_shares >= 0", name="ck_stock_issuance_issued_shares_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["raw.stock_master.stock_id"],
            name="fk_stock_issuance_stock_id_stock_master",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("issuance_id", name="pk_stock_issuance"),
        sa.UniqueConstraint(
            "stock_id", "reference_date", name="uq_stock_issuance_stock_date"
        ),
        schema="raw",
    )
    op.create_index(
        "ix_stock_issuance_stock_date",
        "stock_issuance",
        ["stock_id", "reference_date"],
        schema="raw",
    )
    op.create_index(
        "ix_stock_issuance_date_stock",
        "stock_issuance",
        ["reference_date", "stock_id"],
        schema="raw",
    )

    op.create_table(
        "financial_statement",
        sa.Column(
            "financial_statement_id", sa.BigInteger(), sa.Identity(), nullable=False
        ),
        sa.Column("stock_id", sa.BigInteger()),
        sa.Column("corp_code", sa.String(length=8), nullable=False),
        sa.Column("receipt_number", sa.String(length=20)),
        sa.Column("business_year", sa.String(length=4), nullable=False),
        sa.Column("report_code", sa.String(length=5), nullable=False),
        sa.Column("fiscal_period", sa.String(length=20), nullable=False),
        sa.Column("statement_scope", sa.String(length=3), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("disclosure_date", sa.Date(), nullable=False),
        sa.Column("available_date", sa.Date(), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'KRW'"),
            nullable=False,
        ),
        sa.Column("assets", sa.Numeric(28, 2)),
        sa.Column("current_assets", sa.Numeric(28, 2)),
        sa.Column("liabilities", sa.Numeric(28, 2)),
        sa.Column("current_liabilities", sa.Numeric(28, 2)),
        sa.Column("equity", sa.Numeric(28, 2)),
        sa.Column("revenue", sa.Numeric(28, 2)),
        sa.Column("operating_income", sa.Numeric(28, 2)),
        sa.Column("net_income", sa.Numeric(28, 2)),
        sa.Column("interest_expense", sa.Numeric(28, 2)),
        sa.Column("account_data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "source",
            sa.String(length=100),
            server_default=sa.text("'OPENDART'"),
            nullable=False,
        ),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text())),
        *timestamp_columns(),
        sa.CheckConstraint(
            "available_date >= report_date",
            name="ck_financial_statement_available_date_after_report_date",
        ),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["raw.stock_master.stock_id"],
            name="fk_financial_statement_stock_id_stock_master",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "financial_statement_id", name="pk_financial_statement"
        ),
        sa.UniqueConstraint(
            "corp_code",
            "business_year",
            "report_code",
            "fiscal_period",
            "statement_scope",
            name="uq_financial_statement_period_scope",
        ),
        sa.UniqueConstraint(
            "receipt_number", name="uq_financial_statement_receipt_number"
        ),
        schema="raw",
    )
    op.create_index(
        "ix_financial_statement_stock_available",
        "financial_statement",
        ["stock_id", "available_date"],
        schema="raw",
    )
    op.create_index(
        "ix_financial_statement_available_stock",
        "financial_statement",
        ["available_date", "stock_id"],
        schema="raw",
    )
    op.create_index(
        "ix_financial_statement_corp_period",
        "financial_statement",
        ["corp_code", "business_year", "report_code"],
        schema="raw",
    )

    op.create_table(
        "macro_indicator",
        sa.Column("macro_indicator_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("indicator_code", sa.String(length=100), nullable=False),
        sa.Column("indicator_name", sa.String(length=200)),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("frequency", sa.String(length=10), nullable=False),
        sa.Column("value", sa.Numeric(28, 10), nullable=False),
        sa.Column("unit", sa.String(length=50)),
        sa.Column(
            "source",
            sa.String(length=100),
            server_default=sa.text("'BOK_ECOS'"),
            nullable=False,
        ),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text())),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("macro_indicator_id", name="pk_macro_indicator"),
        sa.UniqueConstraint(
            "indicator_code",
            "observation_date",
            "frequency",
            name="uq_macro_indicator_code_date_frequency",
        ),
        schema="raw",
    )
    op.create_index(
        "ix_macro_indicator_code_date",
        "macro_indicator",
        ["indicator_code", "observation_date"],
        schema="raw",
    )
    op.create_index(
        "ix_macro_indicator_date_code",
        "macro_indicator",
        ["observation_date", "indicator_code"],
        schema="raw",
    )


def downgrade() -> None:
    op.drop_table("macro_indicator", schema="raw")
    op.drop_table("financial_statement", schema="raw")
    op.drop_table("stock_issuance", schema="raw")
    op.drop_table("market_index_daily", schema="raw")
    op.drop_table("stock_price_daily", schema="raw")
    op.drop_table("stock_master", schema="raw")
    op.execute("DROP SCHEMA IF EXISTS processed")
    op.execute("DROP SCHEMA IF EXISTS raw")
