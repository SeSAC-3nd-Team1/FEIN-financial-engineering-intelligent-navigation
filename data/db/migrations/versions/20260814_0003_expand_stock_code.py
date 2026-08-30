"""expand stock code for prefixed KRX identifiers

Revision ID: 20260814_0003
Revises: 20260814_0002
Create Date: 2026-08-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260814_0003"
down_revision: str | None = "20260814_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "stock_master",
        "stock_code",
        schema="raw",
        existing_type=sa.String(length=6),
        type_=sa.String(length=12),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "stock_master",
        "stock_code",
        schema="raw",
        existing_type=sa.String(length=12),
        type_=sa.String(length=6),
        existing_nullable=False,
    )
