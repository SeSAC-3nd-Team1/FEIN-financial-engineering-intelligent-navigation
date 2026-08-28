"""홈 화면 "목표 차량" 위젯의 등급/목표·현재 금액을 계정 단위로 저장한다.

Revision ID: 20260828_0025
Revises: 20260827_0024
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260828_0025"
down_revision: str | None = "20260827_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_car_goals",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("car_grade", sa.String(20), nullable=False),
        sa.Column("goal_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("current_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.CheckConstraint(
            "car_grade IN ('INEX', 'HIGHEND')",
            name="ck_user_car_goals_car_grade_values",
        ),
        sa.CheckConstraint(
            "goal_amount >= 0",
            name="ck_user_car_goals_goal_amount_nonnegative",
        ),
        sa.CheckConstraint(
            "current_amount >= 0",
            name="ck_user_car_goals_current_amount_nonnegative",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_car_goals")
