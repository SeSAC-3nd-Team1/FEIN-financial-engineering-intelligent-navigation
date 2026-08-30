"""투자성향 평가에 결정론적 위험 점수를 저장한다.

Revision ID: 20260828_0028
Revises: 20260828_0027
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260828_0028"
down_revision: str | None = "20260828_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """신규 점수를 추가하되 역산 불가능한 기존 v1 결과는 NULL로 보존한다."""

    op.add_column(
        "investor_profile_assessments",
        sa.Column("risk_score", sa.SmallInteger(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_investor_profile_assessments_risk_score_range"),
        "investor_profile_assessments",
        "risk_score IS NULL OR risk_score BETWEEN 0 AND 100",
    )


def downgrade() -> None:
    """점수 제약을 먼저 제거한 뒤 컬럼을 되돌린다."""

    op.drop_constraint(
        op.f("ck_investor_profile_assessments_risk_score_range"),
        "investor_profile_assessments",
        type_="check",
    )
    op.drop_column("investor_profile_assessments", "risk_score")
