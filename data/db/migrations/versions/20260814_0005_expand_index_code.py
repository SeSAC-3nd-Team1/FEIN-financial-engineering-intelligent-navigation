"""expand index code for series-qualified identifiers

Revision ID: 20260814_0005
Revises: 20260814_0004
Create Date: 2026-08-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260814_0005"
down_revision: str | None = "20260814_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "market_index_daily",
        "index_code",
        schema="raw",
        existing_type=sa.String(length=30),
        type_=sa.String(length=100),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "market_index_daily",
        "index_code",
        schema="raw",
        existing_type=sa.String(length=100),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
