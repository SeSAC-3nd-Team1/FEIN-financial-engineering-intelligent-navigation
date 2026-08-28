"""홈 화면 "목표 차량" 위젯의 계정 단위 상태(등급/목표·현재 금액) service."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import UserCarGoal
from app.schemas.api import CarGrade


class CarGoalService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: int) -> UserCarGoal:
        goal = self.session.get(UserCarGoal, user_id)
        if goal is None:
            raise NotFoundError("CAR_GOAL_NOT_SET", "아직 선택한 차량 등급이 없습니다.")
        return goal

    def upsert(
        self,
        user_id: int,
        car_grade: CarGrade,
        goal_amount: Decimal,
        current_amount: Decimal,
    ) -> UserCarGoal:
        try:
            goal = self.session.get(UserCarGoal, user_id)
            if goal is None:
                goal = UserCarGoal(user_id=user_id)
                self.session.add(goal)
            goal.car_grade = car_grade
            goal.goal_amount = goal_amount
            goal.current_amount = current_amount
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(goal)
        return goal
