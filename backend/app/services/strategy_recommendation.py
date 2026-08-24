"""저장된 투자성향으로 AI 전략 추천을 생성하고 재현 가능한 결과를 보존한다."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ServiceError
from app.integrations.ai.strategy_recommendation_client import StrategyRecommendationAIClient
from app.models import StrategyRecommendation, StrategyRecommendationItem
from app.repositories import RecommendationRepository
from app.schemas.api import (
    StrategyRecommendationAnalysisItem,
    StrategyRecommendationAnalysisResult,
    StrategyRecommendationResponse,
)


class StrategyRecommendationService:
    def __init__(
        self,
        session: Session,
        client: StrategyRecommendationAIClient,
        *,
        model_version: str,
        prompt_version: str,
        strategy_catalog_version: str,
        dataset_version: str,
    ) -> None:
        self.session = session
        self.client = client
        self.model_version = model_version
        self.prompt_version = prompt_version
        self.strategy_catalog_version = strategy_catalog_version
        self.dataset_version = dataset_version
        self.repo = RecommendationRepository(session)

    def _require_ai_consent(self, user_id: int) -> None:
        if not self.repo.has_ai_personalization_consent(user_id):
            raise ServiceError(
                "AI_PERSONALIZATION_CONSENT_REQUIRED",
                "AI 기반 맞춤형 서비스 이용 동의가 필요합니다.",
                403,
            )

    @staticmethod
    def _validate_model_result(
        result: StrategyRecommendationAnalysisResult,
        active_strategy_ids: set[str],
    ) -> list[StrategyRecommendationAnalysisItem]:
        items = sorted(result.recommendations, key=lambda item: item.rank)
        expected_count = min(3, len(active_strategy_ids))
        strategy_ids = [item.strategy_id for item in items]
        ranks = [item.rank for item in items]
        scores = [item.score for item in items]
        if len(items) != expected_count:
            raise ServiceError("AI_INVALID_RECOMMENDATION", "AI 전략 추천 개수가 올바르지 않습니다.", 502)
        if len(set(strategy_ids)) != len(strategy_ids) or not set(strategy_ids).issubset(active_strategy_ids):
            raise ServiceError("AI_INVALID_RECOMMENDATION", "AI가 지원하지 않는 전략을 추천했습니다.", 502)
        if ranks != list(range(1, expected_count + 1)):
            raise ServiceError("AI_INVALID_RECOMMENDATION", "AI 전략 추천 순위가 올바르지 않습니다.", 502)
        if scores != sorted(scores, reverse=True):
            raise ServiceError("AI_INVALID_RECOMMENDATION", "AI 전략 추천 점수와 순위가 일치하지 않습니다.", 502)
        return items

    def _response(self, recommendation: StrategyRecommendation) -> StrategyRecommendationResponse:
        records = self.repo.recommendation_items(recommendation.id)
        if not records:
            raise ServiceError("RECOMMENDATION_DATA_INVALID", "저장된 전략 추천 결과가 올바르지 않습니다.", 500)
        items = [
            StrategyRecommendationAnalysisItem(
                strategy_id=item.strategy_id,
                rank=item.rank,
                score=float(item.score),
                match_level=item.match_level,
                reason=item.reason,
                caution=item.caution,
            )
            for item in records
        ]
        return StrategyRecommendationResponse(
            recommendation_id=recommendation.id,
            assessment_id=recommendation.assessment_id,
            primary=items[0],
            alternatives=items[1:],
            model_version=recommendation.model_version,
            dataset_version=recommendation.dataset_version,
            created_at=recommendation.created_at,
        )

    async def recommend(self, user_id: int, assessment_id: UUID) -> StrategyRecommendationResponse:
        self._require_ai_consent(user_id)
        assessment = self.repo.assessment_for_user(assessment_id, user_id)
        if not assessment:
            raise ServiceError("INVESTOR_PROFILE_NOT_FOUND", "저장된 투자성향을 찾을 수 없습니다.", 404)

        existing = self.repo.recommendation_for_input(
            assessment_id,
            self.model_version,
            self.prompt_version,
            self.strategy_catalog_version,
        )
        if existing:
            return self._response(existing)

        strategies = self.repo.active_strategies()
        if not strategies:
            raise ServiceError("STRATEGY_CATALOG_UNAVAILABLE", "추천할 수 있는 전략이 준비되지 않았습니다.", 503)
        result = await self.client.recommend(assessment, strategies)
        items = self._validate_model_result(result, {strategy.id for strategy in strategies})

        recommendation = StrategyRecommendation(
            id=uuid4(),
            assessment_id=assessment.id,
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            strategy_catalog_version=self.strategy_catalog_version,
            dataset_version=self.dataset_version,
            created_at=datetime.now(UTC),
        )
        try:
            self.session.add(recommendation)
            for item in items:
                self.session.add(StrategyRecommendationItem(
                    recommendation_id=recommendation.id,
                    strategy_id=item.strategy_id,
                    rank=item.rank,
                    score=Decimal(str(item.score)),
                    match_level=item.match_level,
                    reason=item.reason,
                    caution=item.caution,
                ))
            self.session.commit()
        except IntegrityError:
            # 동시 동일 요청은 UNIQUE 계약으로 한 건만 남기고 먼저 저장된 결과를 반환한다.
            self.session.rollback()
            concurrent = self.repo.recommendation_for_input(
                assessment_id,
                self.model_version,
                self.prompt_version,
                self.strategy_catalog_version,
            )
            if concurrent:
                return self._response(concurrent)
            raise
        except Exception:
            self.session.rollback()
            raise
        return self._response(recommendation)

    def latest(self, user_id: int) -> StrategyRecommendationResponse:
        recommendation = self.repo.latest_recommendation(user_id)
        if not recommendation:
            raise ServiceError("STRATEGY_RECOMMENDATION_NOT_FOUND", "저장된 전략 추천을 찾을 수 없습니다.", 404)
        return self._response(recommendation)
