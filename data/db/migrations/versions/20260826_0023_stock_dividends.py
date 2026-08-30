"""OpenDART 연간 배당 원장을 추가한다.

Revision ID: 20260826_0023
Revises: 20260826_0022
Create Date: 2026-08-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260826_0023"
down_revision: str | None = "20260826_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_dividends",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("stock_code", sa.String(12), nullable=False),
        sa.Column(
            "corp_code",
            sa.String(8),
            sa.ForeignKey("companies.corp_code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("business_year", sa.String(4), nullable=False),
        sa.Column("report_code", sa.String(5), nullable=False),
        sa.Column("stock_kind", sa.String(20), nullable=False),
        sa.Column("raw_stock_kind", sa.String(100)),
        sa.Column("dividend_per_share", sa.Numeric(20, 4)),
        sa.Column("reported_dividend_yield", sa.Numeric(12, 6)),
        sa.Column("total_dividend", sa.Numeric(30, 2)),
        sa.Column("dividend_payout_ratio", sa.Numeric(12, 6)),
        sa.Column("receipt_no", sa.String(20)),
        sa.Column("settlement_date", sa.Date()),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column(
            "collected_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "stock_code", "business_year", "report_code", "stock_kind",
            name="uq_stock_dividends_report_kind",
        ),
    )
    op.create_index(
        "ix_stock_dividends_stock_year",
        "stock_dividends",
        ["stock_code", "business_year"],
    )
    op.create_index(
        "ix_stock_dividends_corp_year",
        "stock_dividends",
        ["corp_code", "business_year"],
    )


def downgrade() -> None:
    op.drop_table("stock_dividends")
