"""Price-based model recommendation snapshot API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_session
from app.models import User
from app.schemas.api import (
    ModelRecommendationApplyRequest,
    ModelRecommendationApplyResponse,
    ModelRecommendationSnapshotResponse,
)
from app.services.model_recommendation import ModelRecommendationService
from app.services.momentum_investment import MomentumInvestmentService

router = APIRouter(prefix="/model-recommendations", tags=["model-recommendations"])


def get_model_recommendation_service() -> ModelRecommendationService:
    return ModelRecommendationService()


def get_momentum_investment_service(
    session: Session = Depends(get_session),
) -> MomentumInvestmentService:
    return MomentumInvestmentService(session)


@router.get("/latest", response_model=ModelRecommendationSnapshotResponse)
def latest_model_recommendation(
    _: User = Depends(current_user),
    service: ModelRecommendationService = Depends(get_model_recommendation_service),
) -> ModelRecommendationSnapshotResponse:
    return service.latest()


@router.post("/latest/apply", response_model=ModelRecommendationApplyResponse)
def apply_latest_model_recommendation(
    payload: ModelRecommendationApplyRequest,
    user: User = Depends(current_user),
    service: MomentumInvestmentService = Depends(get_momentum_investment_service),
) -> ModelRecommendationApplyResponse:
    return service.apply(user.id, payload.account_id)
