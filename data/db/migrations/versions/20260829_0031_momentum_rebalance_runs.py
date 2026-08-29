"""Add account and quarter execution guard for momentum v2."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260829_0031"
down_revision: str | None = "20260829_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "momentum_rebalance_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("execution_year", sa.SmallInteger(), nullable=False),
        sa.Column("execution_quarter", sa.SmallInteger(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["virtual_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id", "execution_year", "execution_quarter",
            name="uq_momentum_rebalance_runs_account_quarter",
        ),
        sa.CheckConstraint("execution_quarter BETWEEN 1 AND 4", name="ck_momentum_rebalance_runs_quarter"),
    )


def downgrade() -> None:
    op.drop_table("momentum_rebalance_runs")
