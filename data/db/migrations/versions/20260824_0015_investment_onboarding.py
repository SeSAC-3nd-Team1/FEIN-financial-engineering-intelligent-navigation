"""가상투자 시작 조건과 진행 상태를 저장한다.

Revision ID: 20260824_0015
Revises: 20260824_0014
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0015"
down_revision: str | None = "20260824_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investment_onboardings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("strategy_id", sa.String(30), nullable=False),
        sa.Column("investment_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("operation_mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["account_id"], ["virtual_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_investment_onboardings_user_id"),
        sa.CheckConstraint(
            "investment_amount > 0",
            name="ck_investment_onboardings_investment_amount_positive",
        ),
        sa.CheckConstraint(
            "operation_mode IN ('AUTO', 'SEMI_AUTO')",
            name="ck_investment_onboardings_operation_mode_values",
        ),
        sa.CheckConstraint(
            "status IN ('TERMS_PENDING', 'ACCOUNT_PENDING', 'READY', 'COMPLETED')",
            name="ck_investment_onboardings_status_values",
        ),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND account_id IS NOT NULL AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND completed_at IS NULL)",
            name="ck_investment_onboardings_completion_consistency",
        ),
    )
    op.create_index(
        "ix_investment_onboardings_status",
        "investment_onboardings",
        ["status"],
    )


def downgrade() -> None:
    op.drop_table("investment_onboardings")
