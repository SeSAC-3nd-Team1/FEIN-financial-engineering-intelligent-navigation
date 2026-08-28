"""홈 화면 "목표 차량" 위젯의 계정 단위 상태(등급/목표·현재 금액) service."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import User, UserCarGoal
from app.schemas.api import CarGrade
from app.services.accounts import AccountService
from app.services.portfolio import PortfolioService


class CarGoalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.accounts = AccountService(session)
        self.portfolio = PortfolioService(session)

    def _current_amount(self, user: User) -> Decimal:
        """실제 투자 금액은 클라이언트가 보낸 값이 아니라, 사용자의 현재 활성 운용방식 계좌를
        서버가 직접 조회해 평가한 total_assets만 신뢰한다 — 요청 payload를 그대로 저장하면
        클라이언트가 실제 투자 금액과 다른 값을 임의로 저장할 수 있다(PR #257 리뷰 반영).
        아직 해당 운용방식의 계좌가 없으면(가입 직후 등) 0원으로 취급한다."""
        try:
            account = self.accounts.get_mine(user.id, user.active_operation_mode)
        except NotFoundError:
            return Decimal("0")
        return self.portfolio.evaluate(user.id, account.id).total_assets

    def get(self, user: User) -> UserCarGoal:
        goal = self.session.get(UserCarGoal, user.id)
        if goal is None:
            raise NotFoundError("CAR_GOAL_NOT_SET", "아직 선택한 차량 등급이 없습니다.")
        # DB에 저장된 값이 아니라 조회 시점에 다시 계산한 값을 응답에 결합한다.
        goal.current_amount = self._current_amount(user)
        return goal

    def upsert(self, user: User, car_grade: CarGrade, goal_amount: Decimal) -> UserCarGoal:
        try:
            goal = self.session.get(UserCarGoal, user.id)
            if goal is None:
                goal = UserCarGoal(user_id=user.id)
                self.session.add(goal)
            goal.car_grade = car_grade
            goal.goal_amount = goal_amount
            goal.current_amount = self._current_amount(user)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(goal)
        return goal
