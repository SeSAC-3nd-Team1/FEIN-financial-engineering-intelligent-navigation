"""전략과 무관한 계좌 현금 입금 기록을 추가한다.

Revision ID: 20260828_0026
Revises: 20260828_0025
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260828_0026"
down_revision: str | None = "20260828_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_cash_deposits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(20, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_account_cash_deposits_amount_positive",
        ),
        sa.CheckConstraint(
            "balance_after >= 0",
            name="ck_account_cash_deposits_balance_nonnegative",
        ),
        sa.CheckConstraint(
            "status = 'COMPLETED'",
            name="ck_account_cash_deposits_status_values",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["virtual_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="uq_account_cash_deposits_account_idempotency",
        ),
    )
    op.create_index(
        "ix_account_cash_deposits_account_created",
        "account_cash_deposits",
        ["account_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_cash_deposits_account_created",
        table_name="account_cash_deposits",
    )
    op.drop_table("account_cash_deposits")
