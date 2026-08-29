"""Persist the immutable plan used to retry a momentum rebalance."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260829_0033"
down_revision: str | None = "20260829_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "momentum_rebalance_runs",
        sa.Column("plan", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("momentum_rebalance_runs", "plan")
