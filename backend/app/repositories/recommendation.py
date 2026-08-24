"""투자성향과 전략 추천 이력 조회를 캡슐화한다."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    InvestorProfileAssessment,
    Strategy,
    StrategyRecommendation,
    StrategyRecommendationItem,
    Term,
    UserAgreement,
)


class RecommendationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def has_ai_personalization_consent(self, user_id: int) -> bool:
        statement = (
            select(UserAgreement.id)
            .join(Term, Term.id == UserAgreement.term_id)
            .where(
                UserAgreement.user_id == user_id,
                UserAgreement.is_agreed.is_(True),
                Term.term_code == "AI_PERSONALIZATION",
            )
            .limit(1)
        )
        return self.session.scalar(statement) is not None

    def assessment_for_user(self, assessment_id: UUID, user_id: int) -> InvestorProfileAssessment | None:
        return self.session.scalar(
            select(InvestorProfileAssessment).where(
                InvestorProfileAssessment.id == assessment_id,
                InvestorProfileAssessment.user_id == user_id,
            )
        )

    def latest_assessment(self, user_id: int) -> InvestorProfileAssessment | None:
        return self.session.scalar(
            select(InvestorProfileAssessment)
            .where(InvestorProfileAssessment.user_id == user_id)
            .order_by(InvestorProfileAssessment.created_at.desc(), InvestorProfileAssessment.id.desc())
            .limit(1)
        )

    def active_strategies(self) -> list[Strategy]:
        return list(
            self.session.scalars(
                select(Strategy).where(Strategy.is_active.is_(True)).order_by(Strategy.id)
            )
        )

    def recommendation_for_input(
        self,
        assessment_id: UUID,
        model_version: str,
        prompt_version: str,
        strategy_catalog_version: str,
    ) -> StrategyRecommendation | None:
        return self.session.scalar(
            select(StrategyRecommendation).where(
                StrategyRecommendation.assessment_id == assessment_id,
                StrategyRecommendation.model_version == model_version,
                StrategyRecommendation.prompt_version == prompt_version,
                StrategyRecommendation.strategy_catalog_version == strategy_catalog_version,
            )
        )

    def latest_recommendation(self, user_id: int) -> StrategyRecommendation | None:
        return self.session.scalar(
            select(StrategyRecommendation)
            .join(
                InvestorProfileAssessment,
                InvestorProfileAssessment.id == StrategyRecommendation.assessment_id,
            )
            .where(InvestorProfileAssessment.user_id == user_id)
            .order_by(StrategyRecommendation.created_at.desc(), StrategyRecommendation.id.desc())
            .limit(1)
        )

    def recommendation_items(self, recommendation_id: UUID) -> list[StrategyRecommendationItem]:
        return list(
            self.session.scalars(
                select(StrategyRecommendationItem)
                .where(StrategyRecommendationItem.recommendation_id == recommendation_id)
                .order_by(StrategyRecommendationItem.rank)
            )
        )
