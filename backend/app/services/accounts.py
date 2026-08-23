"""가상계좌 생성과 전략 선택 service."""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, ServiceError
from app.models import CashLedger, VirtualAccount
from app.repositories import TradingRepository


class AccountService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = TradingRepository(session)

    def create(self, user_id: int, account_name: str) -> VirtualAccount:
        try:
            existing = self.repo.account_for_user(user_id)
            if existing:
                raise ServiceError("ACCOUNT_ALREADY_EXISTS", "이미 가상계좌가 존재합니다.", 409)
            account = VirtualAccount(
                user_id=user_id,
                account_name=account_name,
                initial_cash=settings.initial_cash,
                cash_balance=settings.initial_cash,
                status="ACTIVE",
            )
            self.session.add(account)
            self.session.flush()
            self.session.add(CashLedger(
                account_id=account.id,
                transaction_type="INITIAL_DEPOSIT",
                amount=settings.initial_cash,
                balance_after=settings.initial_cash,
                reference_type="ACCOUNT",
                reference_id=str(account.id),
            ))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return account

    def get_mine(self, user_id: int) -> VirtualAccount:
        account = self.repo.account_for_user(user_id)
        if not account:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "가상계좌를 찾을 수 없습니다.")
        return account

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
