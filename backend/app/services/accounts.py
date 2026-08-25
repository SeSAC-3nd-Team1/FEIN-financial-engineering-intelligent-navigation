"""가상계좌 생성과 전략 선택 service."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceError
from app.models import VirtualAccount
from app.repositories import TradingRepository
from app.schemas.api import OperationMode


class AccountService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = TradingRepository(session)

    def create(self, user_id: int, account_name: str, operation_mode: OperationMode) -> VirtualAccount:
        try:
            existing = self.repo.account_for_user(user_id, operation_mode)
            if existing:
                raise ServiceError("ACCOUNT_ALREADY_EXISTS", "해당 운용방식의 가상계좌가 이미 존재합니다.", 409)
            account = VirtualAccount(
                user_id=user_id,
                account_name=account_name,
                operation_mode=operation_mode,
                initial_cash=Decimal("0"),
                cash_balance=Decimal("0"),
                status="ACTIVE",
            )
            self.session.add(account)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return account

    def get_mine(self, user_id: int, operation_mode: OperationMode) -> VirtualAccount:
        account = self.repo.account_for_user(user_id, operation_mode)
        if not account:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "가상계좌를 찾을 수 없습니다.")
        return account

    def get_all_mine(self, user_id: int) -> list[VirtualAccount]:
        return self.repo.accounts_for_user(user_id)

    def select_strategy(self, user_id: int, account_id, strategy_id: str) -> VirtualAccount:
        try:
            account = self.repo.owned_account(account_id, user_id, lock=True)
            if not account:
                raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
            if not self.repo.strategy(strategy_id):
                raise NotFoundError("STRATEGY_NOT_FOUND", "전략을 찾을 수 없습니다.")
            account.selected_strategy_id = strategy_id
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return account
