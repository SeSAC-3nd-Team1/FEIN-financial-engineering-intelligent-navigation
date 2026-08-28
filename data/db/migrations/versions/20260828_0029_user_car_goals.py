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


def _validate_existing_table(bind: sa.engine.Connection) -> None:
    """이미 생성된 목표 차량 테이블이 현재 계약과 일치하는지 검증한다."""

    inspector = sa.inspect(bind)
    columns = {
        column["name"]: column for column in inspector.get_columns("user_car_goals")
    }
    expected_columns = {
        "user_id",
        "car_grade",
        "goal_amount",
        "current_amount",
        "updated_at",
    }
    if set(columns) != expected_columns:
        raise RuntimeError(
            "user_car_goals schema mismatch: expected columns "
            f"{sorted(expected_columns)}, found {sorted(columns)}"
        )
    if columns["user_id"]["nullable"] or columns["car_grade"]["nullable"]:
        raise RuntimeError("user_car_goals required columns must be NOT NULL")
    if columns["goal_amount"]["nullable"] or columns["current_amount"]["nullable"]:
        raise RuntimeError("user_car_goals amount columns must be NOT NULL")
    if columns["updated_at"]["nullable"]:
        raise RuntimeError("user_car_goals.updated_at must be NOT NULL")

    primary_key = inspector.get_pk_constraint("user_car_goals").get(
        "constrained_columns"
    )
    if primary_key != ["user_id"]:
        raise RuntimeError(
            f"user_car_goals primary key mismatch: expected ['user_id'], found {primary_key}"
        )

    foreign_keys = inspector.get_foreign_keys("user_car_goals")
    if not any(
        foreign_key["constrained_columns"] == ["user_id"]
        and foreign_key["referred_table"] == "users"
        and foreign_key["referred_columns"] == ["id"]
        and foreign_key.get("options", {}).get("ondelete") == "CASCADE"
        for foreign_key in foreign_keys
    ):
        raise RuntimeError(
            "user_car_goals.user_id must reference users.id with ON DELETE CASCADE"
        )

    checks = {
        constraint["name"]: " ".join(constraint.get("sqltext", "").split()).lower()
        for constraint in inspector.get_check_constraints("user_car_goals")
    }
    expected_check_tokens = {
        "ck_user_car_goals_car_grade_values": ("car_grade", "inex", "highend"),
        "ck_user_car_goals_goal_amount_nonnegative": ("goal_amount", ">=", "0"),
        "ck_user_car_goals_current_amount_nonnegative": ("current_amount", ">=", "0"),
    }
    for name, tokens in expected_check_tokens.items():
        expression = checks.get(name)
        if expression is None or any(token not in expression for token in tokens):
            raise RuntimeError(
                f"user_car_goals check constraint mismatch: {name}={expression!r}"
            )


def upgrade() -> None:
    # 이 마이그레이션은 원래 "20260828_0025"였는데, develop에 같은 날짜/번호로 만들어진
    # 다른 팀원의 전략 카탈로그 마이그레이션과 revision id가 충돌해 0029로 재배치했다.
    # 공용 DB에는 이미 옛 0025로 이 테이블이 만들어져 있을 수 있으므로, 기존 스키마도
    # 현재 계약과 일치하는지 검증한 뒤에만 migration을 성공 처리한다.
    bind = op.get_bind()
    if sa.inspect(bind).has_table("user_car_goals"):
        _validate_existing_table(bind)
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
