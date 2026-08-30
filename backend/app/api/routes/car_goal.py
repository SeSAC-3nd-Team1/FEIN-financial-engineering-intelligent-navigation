"""홈 화면 "목표 차량" 위젯 상태 API — 계정당 1개, 세션이 아니라 서버에 저장한다."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_session
from app.models import User
from app.schemas.api import CarGoalResponse, CarGoalUpsertRequest
from app.services.car_goal import CarGoalService

router = APIRouter(prefix="/me/car-goal", tags=["car-goal"])


def get_car_goal_service(session: Session = Depends(get_session)) -> CarGoalService:
    return CarGoalService(session)


@router.get("", response_model=CarGoalResponse)
def get_car_goal(
    user: User = Depends(current_user),
    service: CarGoalService = Depends(get_car_goal_service),
) -> CarGoalResponse:
    return service.get(user)


@router.put("", response_model=CarGoalResponse)
def upsert_car_goal(
    payload: CarGoalUpsertRequest,
    user: User = Depends(current_user),
    service: CarGoalService = Depends(get_car_goal_service),
) -> CarGoalResponse:
    return service.upsert(user, payload.car_grade, payload.goal_amount)
