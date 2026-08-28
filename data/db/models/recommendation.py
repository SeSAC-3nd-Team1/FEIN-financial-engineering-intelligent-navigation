"""투자성향 분석과 AI 전략 추천 이력을 정의한다."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID as PythonUUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Numeric, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class InvestorProfileAssessment(Base):
    """원본 설문 대신 AI가 분석한 최소 성향 정보와 재현 버전만 보존한다."""

    __tablename__ = "investor_profile_assessments"
    __table_args__ = (
        CheckConstraint(
            "profile_type IN ('안정추구형', '안정투자형', '중립투자형', '성장추구형', '공격투자형')",
            name="profile_type_values",
        ),
        CheckConstraint("stability BETWEEN 1 AND 5", name="stability_range"),
        CheckConstraint("return_seeking BETWEEN 1 AND 5", name="return_seeking_range"),
        CheckConstraint("horizon BETWEEN 1 AND 5", name="horizon_range"),
        CheckConstraint("risk_score IS NULL OR risk_score BETWEEN 0 AND 100", name="risk_score_range"),
        Index("ix_investor_profile_assessments_user_created", "user_id", "created_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), default=uuid4, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    questionnaire_version: Mapped[str] = mapped_column(String(20), nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(20), nullable=False)
    # v1 AI 분석 기록은 원본 답변을 저장하지 않아 역산할 수 없으므로 nullable로 유지한다.
    risk_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    profile_type: Mapped[str] = mapped_column(String(20), nullable=False)
    stability: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    return_seeking: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    horizon: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tendency_line: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_summary: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StrategyRecommendation(Base):
    """한 투자성향에 대해 특정 학습모델과 전략 catalog가 만든 추천 묶음이다."""

    __tablename__ = "strategy_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "model_version",
            "prompt_version",
            "strategy_catalog_version",
            "dataset_version",
            name="uq_strategy_recommendations_reproducible_input",
        ),
        Index("ix_strategy_recommendations_assessment_created", "assessment_id", "created_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), default=uuid4, primary_key=True)
    assessment_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investor_profile_assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_catalog_version: Mapped[str] = mapped_column(String(50), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StrategyRecommendationItem(Base):
    """추천 묶음 안에서 AI가 정한 전략별 순위·점수·설명을 보존한다."""

    __tablename__ = "strategy_recommendation_items"
    __table_args__ = (
        UniqueConstraint("recommendation_id", "rank", name="uq_strategy_recommendation_items_rank"),
        CheckConstraint("rank BETWEEN 1 AND 3", name="rank_range"),
        CheckConstraint("score >= 0 AND score <= 1", name="score_range"),
        CheckConstraint(
            "match_level IN ('BEST', 'GOOD', 'CAUTION')",
            name="match_level_values",
        ),
    )

    recommendation_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategy_recommendations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    strategy_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("strategies.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    match_level: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    caution: Mapped[str] = mapped_column(Text, nullable=False)
