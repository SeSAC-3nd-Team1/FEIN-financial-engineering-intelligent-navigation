"""저장된 투자성향 기반 AI 전략 추천 API."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import settings
from app.db.session import get_session
from app.integrations.ai import AzureOpenAIStrategyRecommendationClient
from app.models import User
from app.schemas.api import StrategyRecommendationCreateRequest, StrategyRecommendationResponse
from app.services.strategy_recommendation import StrategyRecommendationService

router = APIRouter(prefix="/strategy-recommendations", tags=["strategy-recommendations"])


def get_strategy_recommendation_service(
    session: Session = Depends(get_session),
) -> StrategyRecommendationService:
    client = AzureOpenAIStrategyRecommendationClient(
        endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        deployment=settings.azure_openai_recommendation_deployment,
        api_version=settings.azure_openai_api_version,
        timeout_seconds=settings.ai_recommendation_timeout_seconds,
    )
    return StrategyRecommendationService(
        session,
        client,
        model_version=settings.ai_recommendation_model_version,
        prompt_version=settings.ai_recommendation_prompt_version,
        strategy_catalog_version=settings.strategy_catalog_version,
        dataset_version=settings.ai_recommendation_dataset_version,
    )


@router.post("", response_model=StrategyRecommendationResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy_recommendation(
    payload: StrategyRecommendationCreateRequest,
    user: User = Depends(current_user),
    service: StrategyRecommendationService = Depends(get_strategy_recommendation_service),
) -> StrategyRecommendationResponse:
    return await service.recommend(user.id, payload.assessment_id)


@router.get("/me/latest", response_model=StrategyRecommendationResponse)
def latest_strategy_recommendation(
    user: User = Depends(current_user),
    service: StrategyRecommendationService = Depends(get_strategy_recommendation_service),
) -> StrategyRecommendationResponse:
    return service.latest(user.id)
