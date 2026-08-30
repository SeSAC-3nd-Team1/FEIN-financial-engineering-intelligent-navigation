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
from app.services.loss_avoidance_investment import (
    LossAvoidanceInvestmentService,
    loss_avoidance_snapshot_service,
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


def get_loss_avoidance_investment_service(
    session: Session = Depends(get_session),
) -> LossAvoidanceInvestmentService:
    return LossAvoidanceInvestmentService(session)


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


@router.post("/latest/rebalance", response_model=ModelRecommendationApplyResponse)
def rebalance_latest_model_recommendation(
    payload: ModelRecommendationApplyRequest,
    user: User = Depends(current_user),
    service: MomentumInvestmentService = Depends(get_momentum_investment_service),
) -> ModelRecommendationApplyResponse:
    """Execute only a safe v2 quarterly target against an existing AUTO account."""
    return service.rebalance(user.id, payload.account_id)


@router.get(
    "/loss-avoidance/latest",
    response_model=ModelRecommendationSnapshotResponse,
)
def latest_loss_avoidance_recommendation(
    _: User = Depends(current_user),
) -> ModelRecommendationSnapshotResponse:
    return loss_avoidance_snapshot_service().latest()


@router.post(
    "/loss-avoidance/latest/apply",
    response_model=ModelRecommendationApplyResponse,
)
def apply_latest_loss_avoidance_recommendation(
    payload: ModelRecommendationApplyRequest,
    user: User = Depends(current_user),
    service: LossAvoidanceInvestmentService = Depends(
        get_loss_avoidance_investment_service
    ),
) -> ModelRecommendationApplyResponse:
    return service.apply(user.id, payload.account_id)


@router.post(
    "/loss-avoidance/latest/rebalance",
    response_model=ModelRecommendationApplyResponse,
)
def rebalance_latest_loss_avoidance_recommendation(
    payload: ModelRecommendationApplyRequest,
    user: User = Depends(current_user),
    service: LossAvoidanceInvestmentService = Depends(
        get_loss_avoidance_investment_service
    ),
) -> ModelRecommendationApplyResponse:
    return service.rebalance(user.id, payload.account_id)
