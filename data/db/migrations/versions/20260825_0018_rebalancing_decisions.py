"""리밸런싱 판단 이력을 추가한다.

Revision ID: 20260825_0018
Revises: 20260825_0017
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260825_0018"
down_revision: str | None = "20260825_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """서버 제안값과 사용자 선택, 결과 계산의 기준 자산을 함께 보존한다."""

    op.create_table(
        "rebalancing_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", sa.String(30)),
        sa.Column("stock_code", sa.String(12), nullable=False),
        sa.Column("stock_name", sa.String(200)),
        sa.Column("action", sa.String(4), nullable=False),
        sa.Column("current_weight", sa.Numeric(9, 4), nullable=False),
        sa.Column("target_weight", sa.Numeric(9, 4), nullable=False),
        sa.Column("weight_diff", sa.Numeric(9, 4), nullable=False),
        sa.Column("recommended_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("baseline_snapshot_date", sa.Date()),
        sa.Column("baseline_total_assets", sa.Numeric(20, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("action IN ('BUY', 'SELL')", name="action_values"),
        sa.CheckConstraint("decision IN ('ACCEPTED', 'HELD')", name="decision_values"),
        sa.ForeignKeyConstraint(["account_id"], ["virtual_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_rebalancing_decisions_account_idempotency"),
    )
    op.create_index(
        "ix_rebalancing_decisions_account_created",
        "rebalancing_decisions",
        ["account_id", "created_at"],
    )


def downgrade() -> None:
    """판단 이력 테이블만 제거하고 기존 거래·평가 데이터는 유지한다."""

    op.drop_table("rebalancing_decisions")
