"""투자성향 분석 및 AI 전략 추천 이력 테이블을 추가한다.

Revision ID: 20260824_0014
Revises: 20260824_0013
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0014"
down_revision: str | None = "20260824_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investor_profile_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("questionnaire_version", sa.String(20), nullable=False),
        sa.Column("analysis_version", sa.String(20), nullable=False),
        sa.Column("profile_type", sa.String(20), nullable=False),
        sa.Column("stability", sa.SmallInteger(), nullable=False),
        sa.Column("return_seeking", sa.SmallInteger(), nullable=False),
        sa.Column("horizon", sa.SmallInteger(), nullable=False),
        sa.Column("tendency_line", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("analysis_summary", postgresql.JSONB(), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "profile_type IN ('안정추구형', '안정투자형', '중립투자형', '성장추구형', '공격투자형')",
            name="ck_investor_profile_assessments_profile_type_values",
        ),
        sa.CheckConstraint("stability BETWEEN 1 AND 5", name="ck_investor_profile_assessments_stability_range"),
        sa.CheckConstraint("return_seeking BETWEEN 1 AND 5", name="ck_investor_profile_assessments_return_seeking_range"),
        sa.CheckConstraint("horizon BETWEEN 1 AND 5", name="ck_investor_profile_assessments_horizon_range"),
    )
    op.create_index(
        "ix_investor_profile_assessments_user_created",
        "investor_profile_assessments",
        ["user_id", "created_at"],
    )

    op.create_table(
        "strategy_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("strategy_catalog_version", sa.String(50), nullable=False),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["investor_profile_assessments.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "assessment_id",
            "model_version",
            "prompt_version",
            "strategy_catalog_version",
            "dataset_version",
            name="uq_strategy_recommendations_reproducible_input",
        ),
    )
    op.create_index(
        "ix_strategy_recommendations_assessment_created",
        "strategy_recommendations",
        ["assessment_id", "created_at"],
    )

    op.create_table(
        "strategy_recommendation_items",
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", sa.String(30), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column("match_level", sa.String(10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("caution", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["strategy_recommendations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("recommendation_id", "strategy_id"),
        sa.UniqueConstraint("recommendation_id", "rank", name="uq_strategy_recommendation_items_rank"),
        sa.CheckConstraint("rank BETWEEN 1 AND 3", name="ck_strategy_recommendation_items_rank_range"),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="ck_strategy_recommendation_items_score_range"),
        sa.CheckConstraint(
            "match_level IN ('BEST', 'GOOD', 'CAUTION')",
            name="ck_strategy_recommendation_items_match_level_values",
        ),
    )


def downgrade() -> None:
    # 추천 상세부터 제거해 외래키 순서를 지킨다.
    op.drop_table("strategy_recommendation_items")
    op.drop_table("strategy_recommendations")
    op.drop_table("investor_profile_assessments")
