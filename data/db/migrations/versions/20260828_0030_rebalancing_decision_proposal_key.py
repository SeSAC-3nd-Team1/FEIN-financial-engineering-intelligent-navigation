"""리밸런싱 제안 단위 중복 판단 방지 키를 추가한다."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260828_0030"
down_revision: str | None = "20260828_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rebalancing_decisions",
        sa.Column("proposal_key", sa.String(255), nullable=True),
    )
    bind = op.get_bind()
    op.execute(
        sa.text(
            "UPDATE rebalancing_decisions "
            "SET proposal_key = idempotency_key "
            "WHERE proposal_key IS NULL"
        )
    )
    op.alter_column("rebalancing_decisions", "proposal_key", nullable=False)
    op.create_unique_constraint(
        "uq_rebalancing_decisions_account_proposal",
        "rebalancing_decisions",
        ["account_id", "proposal_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_rebalancing_decisions_account_proposal",
        "rebalancing_decisions",
        type_="unique",
    )
    op.drop_column("rebalancing_decisions", "proposal_key")
