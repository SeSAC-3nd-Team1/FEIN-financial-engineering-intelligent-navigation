"""OpenDART 기업·재무·공시 테이블을 추가한다.

Revision ID: 20260824_0013
Revises: 20260823_0012
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260824_0013"
down_revision: str | None = "20260823_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("corp_code", sa.String(8), nullable=False, unique=True),
        sa.Column("stock_code", sa.String(12)),
        sa.Column("corp_name", sa.String(200), nullable=False),
        sa.Column("corp_name_eng", sa.String(200)),
        sa.Column("stock_name", sa.String(200)),
        sa.Column("market", sa.String(10)),
        sa.Column("ceo_name", sa.String(200)),
        sa.Column("jurir_no", sa.String(20)),
        sa.Column("bizr_no", sa.String(20)),
        sa.Column("address", sa.Text()),
        sa.Column("homepage_url", sa.Text()),
        sa.Column("ir_url", sa.Text()),
        sa.Column("phone_number", sa.String(100)),
        sa.Column("industry_code", sa.String(20)),
        sa.Column("established_date", sa.Date()),
        sa.Column("accounting_month", sa.String(2)),
        sa.Column("dart_modify_date", sa.Date()),
        *_timestamps(),
    )
    op.create_index("ix_companies_stock_code", "companies", ["stock_code"])
    op.create_index("ix_companies_corp_name", "companies", ["corp_name"])

    op.create_table(
        "company_financial_accounts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("corp_code", sa.String(8), sa.ForeignKey("companies.corp_code", ondelete="RESTRICT"), nullable=False),
        sa.Column("stock_code", sa.String(12)),
        sa.Column("business_year", sa.String(4), nullable=False),
        sa.Column("report_code", sa.String(5), nullable=False),
        sa.Column("fs_div", sa.String(10), nullable=False),
        sa.Column("sj_div", sa.String(10), nullable=False),
        sa.Column("account_id", sa.String(200), nullable=False),
        sa.Column("account_name", sa.String(200), nullable=False),
        sa.Column("current_amount", sa.Numeric(30, 2)),
        sa.Column("previous_amount", sa.Numeric(30, 2)),
        sa.Column("currency", sa.String(10), server_default="KRW", nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("corp_code", "business_year", "report_code", "fs_div", "sj_div", "account_id", name="uq_financial_accounts_identity"),
    )
    op.create_index("ix_financial_accounts_stock_year", "company_financial_accounts", ["stock_code", "business_year"])
    op.create_index("ix_financial_accounts_corp_year", "company_financial_accounts", ["corp_code", "business_year"])

    op.create_table(
        "company_financials",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("corp_code", sa.String(8), sa.ForeignKey("companies.corp_code", ondelete="RESTRICT"), nullable=False),
        sa.Column("stock_code", sa.String(12)),
        sa.Column("business_year", sa.String(4), nullable=False),
        sa.Column("report_code", sa.String(5), nullable=False),
        sa.Column("quarter", sa.String(10), nullable=False),
        sa.Column("fs_div", sa.String(10), nullable=False),
        sa.Column("revenue", sa.Numeric(30, 2)),
        sa.Column("operating_income", sa.Numeric(30, 2)),
        sa.Column("net_income", sa.Numeric(30, 2)),
        sa.Column("total_assets", sa.Numeric(30, 2)),
        sa.Column("total_liabilities", sa.Numeric(30, 2)),
        sa.Column("total_equity", sa.Numeric(30, 2)),
        sa.Column("operating_cash_flow", sa.Numeric(30, 2)),
        sa.Column("investing_cash_flow", sa.Numeric(30, 2)),
        sa.Column("financing_cash_flow", sa.Numeric(30, 2)),
        *_timestamps(),
        sa.UniqueConstraint("corp_code", "business_year", "report_code", "fs_div", name="uq_company_financials_report"),
    )
    op.create_index("ix_company_financials_stock_year", "company_financials", ["stock_code", "business_year"])

    op.create_table(
        "company_disclosures",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("receipt_no", sa.String(20), nullable=False, unique=True),
        sa.Column("corp_code", sa.String(8), sa.ForeignKey("companies.corp_code", ondelete="RESTRICT"), nullable=False),
        sa.Column("stock_code", sa.String(12)),
        sa.Column("corp_name", sa.String(200), nullable=False),
        sa.Column("report_name", sa.String(500), nullable=False),
        sa.Column("filer_name", sa.String(200)),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("remarks", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_company_disclosures_corp_code", "company_disclosures", ["corp_code"])
    op.create_index("ix_company_disclosures_stock_code", "company_disclosures", ["stock_code"])
    op.create_index("ix_company_disclosures_receipt_date", "company_disclosures", ["receipt_date"])


def downgrade() -> None:
    # 자식 테이블부터 제거해 RESTRICT 외래키 순서를 지킨다.
    op.drop_table("company_disclosures")
    op.drop_table("company_financials")
    op.drop_table("company_financial_accounts")
    op.drop_table("companies")
