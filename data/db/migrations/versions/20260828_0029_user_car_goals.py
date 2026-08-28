"""홈 화면 "목표 차량" 위젯의 등급/목표·현재 금액을 계정 단위로 저장한다.

Revision ID: 20260828_0029
Revises: 20260828_0028
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260828_0029"
down_revision: str | None = "20260828_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 이 마이그레이션은 원래 "20260828_0025"였는데, develop에 같은 날짜/번호로 만들어진
    # 다른 팀원의 전략 카탈로그 마이그레이션과 revision id가 충돌해 0029로 재배치했다.
    # 공용 DB에는 이미 옛 0025로 이 테이블이 만들어져 있으므로(신규 개발 환경만 여기서 새로
    # 만들면 된다), 존재 여부를 먼저 확인해 중복 생성 에러 없이 멱등하게 만든다.
    bind = op.get_bind()
    if sa.inspect(bind).has_table("user_car_goals"):
        return
    op.create_table(
        "user_car_goals",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("car_grade", sa.String(20), nullable=False),
        sa.Column("goal_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("current_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
    bind = op.get_bind()
    if sa.inspect(bind).has_table("user_car_goals"):
        op.drop_table("user_car_goals")
