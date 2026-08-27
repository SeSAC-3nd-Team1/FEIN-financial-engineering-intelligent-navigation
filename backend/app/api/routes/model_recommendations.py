"""Price-based model recommendation snapshot API."""

from fastapi import APIRouter, Depends

from app.api.deps import current_user
from app.models import User
from app.schemas.api import ModelRecommendationSnapshotResponse
from app.services.model_recommendation import ModelRecommendationService

router = APIRouter(prefix="/model-recommendations", tags=["model-recommendations"])


def get_model_recommendation_service() -> ModelRecommendationService:
    return ModelRecommendationService()


@router.get("/latest", response_model=ModelRecommendationSnapshotResponse)
def latest_model_recommendation(
    _: User = Depends(current_user),
    service: ModelRecommendationService = Depends(get_model_recommendation_service),
) -> ModelRecommendationSnapshotResponse:
    return service.latest()
