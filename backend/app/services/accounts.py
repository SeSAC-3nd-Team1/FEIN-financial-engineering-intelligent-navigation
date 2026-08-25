"""가상계좌 생성, 전략 선택과 활성 운용방식 전환 service."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceError
from app.models import VirtualAccount
from app.repositories import TradingRepository
from app.schemas.api import (
    OperationMode,
    OperationModeChangeNoticeResponse,
    OperationModeSwitchResponse,
)


OPERATION_MODE_LABELS: dict[OperationMode, str] = {
    "AUTO": "자동으로 운용",
    "SEMI_AUTO": "확인하고 실행",
}


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

    def switch_active_operation_mode(
        self,
        user_id: int,
        operation_mode: OperationMode,
    ) -> OperationModeSwitchResponse:
        """운용방식별 계좌를 보존한 채 현재 활성 계좌 선택만 변경한다."""

        try:
            user = self.repo.user(user_id, lock=True)
            if user is None:
                raise NotFoundError("USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
            account = self.repo.account_for_user(user_id, operation_mode, lock=True)
            if account is None:
                raise ServiceError(
                    "OPERATION_MODE_ACCOUNT_NOT_READY",
                    "해당 운용방식의 가상계좌가 없습니다. 먼저 투자 시작을 완료해 주세요.",
                    409,
                )
            onboarding = self.repo.completed_onboarding_for_user_mode(
                user_id,
                operation_mode,
            )
            if onboarding is None or onboarding.account_id != account.id:
                raise ServiceError(
                    "OPERATION_MODE_ACCOUNT_NOT_READY",
                    "해당 운용방식의 투자 시작을 먼저 완료해 주세요.",
                    409,
                )
            if account.status != "ACTIVE":
                raise ServiceError(
                    "OPERATION_MODE_ACCOUNT_NOT_ACTIVE",
                    "해당 운용방식의 가상계좌를 사용할 수 없습니다.",
                    409,
                )

            previous = user.active_operation_mode
            changed = previous != operation_mode
            if changed:
                user.active_operation_mode = operation_mode
                user.operation_mode_changed_at = datetime.now(UTC)
                self.session.commit()
                self.session.refresh(user)

            return OperationModeSwitchResponse(
                previous_operation_mode=previous,
                operation_mode=operation_mode,
                changed=changed,
                changed_at=user.operation_mode_changed_at,
                account=account,
                notice=self._operation_mode_notice(previous, operation_mode, changed),
            )
        except Exception:
            self.session.rollback()
            raise

    @staticmethod
    def _operation_mode_notice(
        previous: OperationMode | None,
        operation_mode: OperationMode,
        changed: bool,
    ) -> OperationModeChangeNoticeResponse:
        target_label = OPERATION_MODE_LABELS[operation_mode]
        if not changed:
            return OperationModeChangeNoticeResponse(
                code="OPERATION_MODE_UNCHANGED",
                title="현재 운용방식이에요",
                message=f"이미 {target_label} 계좌를 사용 중이에요.",
            )
        if previous is None:
            message = f"{target_label} 계좌를 현재 운용방식으로 설정했어요."
        else:
            previous_label = OPERATION_MODE_LABELS[previous]
            message = (
                f"{previous_label} 계좌에서 {target_label} 계좌로 전환했어요. "
                "각 계좌의 자산과 거래내역은 이동하지 않고 그대로 유지됩니다."
            )
        return OperationModeChangeNoticeResponse(
            code="OPERATION_MODE_CHANGED",
            title="운용방식이 변경됐어요",
            message=message,
        )

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
