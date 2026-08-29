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
    if bind.dialect.name != "postgresql":
        raise RuntimeError("rebalancing proposal key migration requires PostgreSQL")
    op.execute(sa.text("""
            WITH canonical AS (
                SELECT id, account_id, created_at,
                       concat_ws('|',
                           coalesce(strategy_id, ''), stock_code, action,
                           to_char(current_weight, 'FM999999999999990.00'),
                           to_char(target_weight, 'FM999999999999990.00'),
                           to_char(weight_diff, 'FM999999999999990.00'),
                           to_char(recommended_amount, 'FM9999999999999999990.00'),
                           coalesce(baseline_snapshot_date, created_at::date, current_date)
                       ) AS key
                FROM rebalancing_decisions
            ), ranked AS (
                SELECT canonical.*,
                       row_number() OVER (
                           PARTITION BY account_id, key
                           ORDER BY created_at, id
                       ) AS duplicate_rank
                FROM canonical
            )
            DELETE FROM rebalancing_decisions decision
            USING ranked duplicate
            WHERE decision.id = duplicate.id
              AND duplicate.duplicate_rank > 1
            """))
    op.execute(sa.text("""
            UPDATE rebalancing_decisions decision
            SET proposal_key = ranked.key
            FROM (
                SELECT id,
                       concat_ws('|',
                           coalesce(strategy_id, ''), stock_code, action,
                           to_char(current_weight, 'FM999999999999990.00'),
                           to_char(target_weight, 'FM999999999999990.00'),
                           to_char(weight_diff, 'FM999999999999990.00'),
                           to_char(recommended_amount, 'FM9999999999999999990.00'),
                           coalesce(baseline_snapshot_date, created_at::date, current_date)
                       ) AS key
                FROM rebalancing_decisions
            ) ranked
            WHERE decision.id = ranked.id
            """))
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
