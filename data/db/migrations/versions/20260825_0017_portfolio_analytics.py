"""포트폴리오 스냅샷과 전략 목표 비중을 추가한다.

Revision ID: 20260825_0017
Revises: 20260824_0016
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260825_0017"
down_revision: str | None = "20260824_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """실제 계좌 평가 이력과 명시적 전략 목표 비중을 저장한다."""

    op.create_table(
        "strategy_target_weights",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("strategy_id", sa.String(30), nullable=False),
        sa.Column("stock_code", sa.String(12), nullable=False),
        sa.Column("target_weight", sa.Numeric(9, 8), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "strategy_id",
            "stock_code",
            "effective_from",
            name="uq_strategy_target_weights_version",
        ),
        sa.CheckConstraint(
            "target_weight >= 0 AND target_weight <= 1",
            name="ck_strategy_target_weights_range",
        ),
    )
    op.create_index(
        "ix_strategy_target_weights_strategy_effective",
        "strategy_target_weights",
        ["strategy_id", "effective_from"],
    )

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("cash_balance", sa.Numeric(20, 2), nullable=False),
        sa.Column("total_purchase_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("total_evaluation_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("total_assets", sa.Numeric(20, 2), nullable=False),
        sa.Column("unrealized_profit", sa.Numeric(20, 2), nullable=False),
        sa.Column("realized_profit", sa.Numeric(20, 2), nullable=False),
        sa.Column("return_rate", sa.Numeric(12, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["virtual_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("account_id", "snapshot_date", name="uq_portfolio_snapshots_account_date"),
    )
    op.create_index(
        "ix_portfolio_snapshots_account_date",
        "portfolio_snapshots",
        ["account_id", "snapshot_date"],
    )


def downgrade() -> None:
    """이번 revision이 추가한 분석용 테이블만 제거한다."""

    op.drop_table("portfolio_snapshots")
    op.drop_table("strategy_target_weights")
