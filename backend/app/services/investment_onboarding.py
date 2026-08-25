"""투자 약관 동의와 가상계좌 준비를 하나의 서버 상태로 관리한다."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceError
from app.models import AccountDeposit, CashLedger, InvestmentOnboarding, Strategy, Term, User, UserAgreement, VirtualAccount
from app.schemas.api import (
    InvestmentAccountPrepareResponse,
    InvestmentAgreementSubmitRequest,
    InvestmentDepositRequest,
    InvestmentDepositResponse,
    InvestmentOnboardingCreateRequest,
    InvestmentOnboardingResponse,
    OperationMode,
)


GENERIC_INVESTMENT_TERM_CODES = (
    "INVEST_SERVICE",
    "INVEST_PRIVACY",
    "INVEST_LOSS_NOTICE",
)


def investment_product_term_code(strategy_id: str) -> str:
    """전략별 상품설명서가 독립적으로 버전 관리되도록 약관 코드를 만든다."""

    code = f"INVEST_PRODUCT_{strategy_id.upper()}"
    if len(code) > 30:
        raise ServiceError("INVALID_STRATEGY_ID", "상품설명서 코드로 사용할 수 없는 전략 ID입니다.")
    return code


def investment_term_codes(strategy_id: str) -> tuple[str, ...]:
    return (investment_product_term_code(strategy_id), *GENERIC_INVESTMENT_TERM_CODES)


class InvestmentOnboardingService:
    """투자 조건, 최신 약관 동의, 가상계좌 준비와 최종 확정을 조율한다."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def terms(self, strategy_id: str) -> list[Term]:
        self._active_strategy(strategy_id)
        return self._current_terms(strategy_id)

    def create_or_update(
        self,
        user: User,
        request: InvestmentOnboardingCreateRequest,
    ) -> InvestmentOnboardingResponse:
        self._ensure_verified_user(user)
        self._active_strategy(request.strategy_id)
        onboarding = self.session.scalar(
            select(InvestmentOnboarding)
            .where(
                InvestmentOnboarding.user_id == user.id,
                InvestmentOnboarding.operation_mode == request.operation_mode,
            )
            .with_for_update()
        )
        unchanged_completed = bool(
            onboarding
            and onboarding.status == "COMPLETED"
            and onboarding.strategy_id == request.strategy_id
            and onboarding.investment_amount == request.investment_amount
            and onboarding.operation_mode == request.operation_mode
        )
        try:
            if onboarding is None:
                onboarding = InvestmentOnboarding(
                    user_id=user.id,
                    strategy_id=request.strategy_id,
                    investment_amount=request.investment_amount,
                    operation_mode=request.operation_mode,
                    status="TERMS_PENDING",
                )
                self.session.add(onboarding)
            if not unchanged_completed:
                onboarding.strategy_id = request.strategy_id
                onboarding.investment_amount = request.investment_amount
                onboarding.completed_at = None
                account = self._account_for_user(user.id, request.operation_mode)
                onboarding.account_id = account.id if account else None
                if not self._has_current_agreements(user.id, request.strategy_id):
                    onboarding.status = "TERMS_PENDING"
                elif account is None:
                    onboarding.status = "ACCOUNT_PENDING"
                elif self._required_deposit(onboarding.investment_amount, account.cash_balance) > 0:
                    onboarding.status = "DEPOSIT_PENDING"
                else:
                    onboarding.status = "READY"
            self.session.flush()
            self.session.commit()
            self.session.refresh(onboarding)
        except Exception:
            self.session.rollback()
            raise
        return self._response(onboarding)

    def current(self, user_id: int, operation_mode: OperationMode) -> InvestmentOnboardingResponse:
        onboarding = self._owned_onboarding_for_user(user_id, operation_mode)
        return self._response(onboarding)

    def currents(self, user_id: int) -> list[InvestmentOnboardingResponse]:
        onboardings = self.session.scalars(
            select(InvestmentOnboarding)
            .where(InvestmentOnboarding.user_id == user_id)
            .order_by(InvestmentOnboarding.operation_mode)
        )
        return [self._response(onboarding) for onboarding in onboardings]

    def agree(
        self,
        user_id: int,
        onboarding_id: UUID,
        request: InvestmentAgreementSubmitRequest,
        *,
        agreed_ip: str | None,
        user_agent: str | None,
    ) -> InvestmentOnboardingResponse:
        onboarding = self._owned_onboarding(user_id, onboarding_id, lock=True)
        catalog = self._current_terms(onboarding.strategy_id)
        preserve_completed = (
            onboarding.status == "COMPLETED"
            and self._has_current_agreements(user_id, onboarding.strategy_id)
        )
        catalog_by_key = {(term.term_code, term.version): term for term in catalog}
        submitted_keys = [(item.term_code, item.version) for item in request.agreements]
        if len(submitted_keys) != len(set(submitted_keys)):
            raise ServiceError("DUPLICATE_AGREEMENT", "같은 약관을 중복 제출할 수 없습니다.")
        if any(key not in catalog_by_key for key in submitted_keys):
            raise ServiceError("INVALID_TERM_VERSION", "존재하지 않거나 현재 유효하지 않은 약관 버전입니다.")
        accepted = {
            (item.term_code, item.version)
            for item in request.agreements
            if item.agreed
        }
        required = {
            (term.term_code, term.version)
            for term in catalog
            if term.is_required
        }
        if not required.issubset(accepted):
            raise ServiceError("INVESTMENT_TERMS_NOT_AGREED", "투자 필수 약관에 모두 동의해야 합니다.")

        now = datetime.now(UTC)
        term_ids = [catalog_by_key[key].id for key in submitted_keys]
        existing = {
            agreement.term_id: agreement
            for agreement in self.session.scalars(
                select(UserAgreement).where(
                    UserAgreement.user_id == user_id,
                    UserAgreement.term_id.in_(term_ids),
                )
            )
        }
        try:
            for item in request.agreements:
                term = catalog_by_key[(item.term_code, item.version)]
                agreement = existing.get(term.id)
                if agreement is None:
                    agreement = UserAgreement(user_id=user_id, term_id=term.id)
                    self.session.add(agreement)
                agreement.is_agreed = item.agreed
                agreement.agreed_at = now if item.agreed else None
                agreement.agreed_ip = agreed_ip
                agreement.user_agent = user_agent[:512] if user_agent else None
            account = self._account_for_user(user_id, onboarding.operation_mode)
            keep_completed_state = bool(
                preserve_completed and account and onboarding.account_id == account.id
            )
            onboarding.account_id = account.id if account else None
            if not keep_completed_state:
                if account is None:
                    onboarding.status = "ACCOUNT_PENDING"
                elif self._required_deposit(onboarding.investment_amount, account.cash_balance) > 0:
                    onboarding.status = "DEPOSIT_PENDING"
                else:
                    onboarding.status = "READY"
                onboarding.completed_at = None
            self.session.commit()
            self.session.refresh(onboarding)
        except Exception:
            self.session.rollback()
            raise
        return self._response(onboarding)

    def prepare_account(
        self,
        user: User,
        onboarding_id: UUID,
        account_name: str,
    ) -> InvestmentAccountPrepareResponse:
        self._ensure_verified_user(user)
        onboarding = self._owned_onboarding(user.id, onboarding_id, lock=True)
        self._require_current_agreements(user.id, onboarding.strategy_id)
        account = self._account_for_user(user.id, onboarding.operation_mode, lock=True)
        created = False
        try:
            if account is None:
                # 계좌 준비와 입금을 분리해야 사용자가 화면에서 확정한 부족분만 원장에 남는다.
                account = VirtualAccount(
                    user_id=user.id,
                    account_name=account_name.strip(),
                    operation_mode=onboarding.operation_mode,
                    initial_cash=Decimal("0"),
                    cash_balance=Decimal("0"),
                    status="ACTIVE",
                )
                self.session.add(account)
                self.session.flush()
                created = True
            # 기존 계좌는 포지션과 append-only 원장 정합성을 위해 잔액·계좌명을 유지한다.
            # 선택 금액을 추가 입금하거나 계좌를 초기화하지 않고 완료 단계에서 가용 현금만 검증한다.
            elif account.status != "ACTIVE":
                raise ServiceError("ACCOUNT_NOT_ACTIVE", "사용할 수 없는 가상계좌입니다.", 409)
            onboarding.account_id = account.id
            if onboarding.status != "COMPLETED":
                onboarding.status = (
                    "DEPOSIT_PENDING"
                    if self._required_deposit(onboarding.investment_amount, account.cash_balance) > 0
                    else "READY"
                )
                onboarding.completed_at = None
            self.session.commit()
            self.session.refresh(account)
            self.session.refresh(onboarding)
        except Exception:
            self.session.rollback()
            raise
        return InvestmentAccountPrepareResponse(
            account=account,
            created=created,
            required_deposit_amount=self._required_deposit(
                onboarding.investment_amount,
                account.cash_balance,
            ),
            onboarding=self._response(onboarding),
        )

    def deposit(
        self,
        user_id: int,
        onboarding_id: UUID,
        request: InvestmentDepositRequest,
    ) -> InvestmentDepositResponse:
        """현재 부족분과 정확히 같은 가상 투자금을 계좌에 한 번만 반영한다."""

        onboarding = self._owned_onboarding(user_id, onboarding_id, lock=True)
        self._require_current_agreements(user_id, onboarding.strategy_id)
        account = self._account_for_user(user_id, onboarding.operation_mode, lock=True)
        if account is None or onboarding.account_id != account.id:
            raise ServiceError("ACCOUNT_NOT_READY", "가상계좌 준비를 먼저 완료해야 합니다.", 409)
        if account.status != "ACTIVE":
            raise ServiceError("ACCOUNT_NOT_ACTIVE", "사용할 수 없는 가상계좌입니다.", 409)

        existing = self._deposit_for_key(account.id, request.idempotency_key)
        if existing is not None:
            if existing.onboarding_id != onboarding.id or Decimal(existing.amount) != Decimal(request.amount):
                raise ServiceError(
                    "DEPOSIT_IDEMPOTENCY_CONFLICT",
                    "같은 멱등성 키를 다른 입금 요청에 사용할 수 없습니다.",
                    409,
                )
            return self._deposit_response(existing, onboarding)

        required = self._required_deposit(onboarding.investment_amount, account.cash_balance)
        if required == 0:
            raise ServiceError("DEPOSIT_NOT_REQUIRED", "추가로 입금할 가상 투자금이 없습니다.", 409)
        if Decimal(request.amount) != required:
            raise ServiceError(
                "INVALID_DEPOSIT_AMOUNT",
                f"현재 필요한 입금액 {required}원을 정확히 입력해야 합니다.",
                409,
            )

        now = datetime.now(UTC)
        deposit = AccountDeposit(
            id=uuid4(),
            account_id=account.id,
            onboarding_id=onboarding.id,
            amount=required,
            balance_after=Decimal(account.cash_balance) + required,
            status="COMPLETED",
            idempotency_key=request.idempotency_key,
            completed_at=now,
        )
        try:
            account.cash_balance = deposit.balance_after
            # 신규 0원 계좌의 첫 입금만 최초 투자금으로 기록한다. 이후 거래로 현금이 줄어도
            # initial_cash는 바꾸지 않아 계좌가 시작한 금액을 보존한다.
            if Decimal(account.initial_cash) == 0:
                account.initial_cash = required
            self.session.add(deposit)
            self.session.add(CashLedger(
                account_id=account.id,
                transaction_type="DEPOSIT",
                amount=required,
                balance_after=account.cash_balance,
                reference_type="DEPOSIT",
                reference_id=str(deposit.id),
            ))
            onboarding.status = "READY"
            onboarding.completed_at = None
            self.session.commit()
            self.session.refresh(deposit)
            self.session.refresh(account)
            self.session.refresh(onboarding)
        except Exception:
            self.session.rollback()
            raise
        return self._deposit_response(deposit, onboarding)

    def complete(self, user_id: int, onboarding_id: UUID) -> InvestmentOnboardingResponse:
        try:
            # 운용방식 전환과 공통으로 User를 가장 먼저 잠가 두 요청의 lock 순서를 통일한다.
            user = self.session.scalar(
                select(User).where(User.id == user_id).with_for_update()
            )
            if user is None:
                raise NotFoundError("USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
            onboarding = self._owned_onboarding(user_id, onboarding_id, lock=True)
            was_completed = onboarding.status == "COMPLETED"
            self._require_current_agreements(user_id, onboarding.strategy_id)
            account = self._account_for_user(user_id, onboarding.operation_mode, lock=True)
            if account is None or onboarding.account_id != account.id:
                raise ServiceError("ACCOUNT_NOT_READY", "가상계좌 준비를 먼저 완료해야 합니다.", 409)
            if account.status != "ACTIVE":
                raise ServiceError("ACCOUNT_NOT_ACTIVE", "사용할 수 없는 가상계좌입니다.", 409)
            if Decimal(account.cash_balance) < Decimal(onboarding.investment_amount):
                raise ServiceError(
                    "INSUFFICIENT_VIRTUAL_CASH",
                    "가상계좌 현금이 투자 예정 금액보다 부족합니다.",
                    409,
                )
            self._active_strategy(onboarding.strategy_id)
            now = datetime.now(UTC)
            account.selected_strategy_id = onboarding.strategy_id
            onboarding.status = "COMPLETED"
            onboarding.completed_at = onboarding.completed_at or now
            # 새 운용방식의 투자 시작을 완료한 경우 그 계좌를 현재 선택으로 삼는다. 이미 완료된
            # 요청의 재전송은 사용자가 이후 명시적으로 전환한 선택을 되돌리지 않는다.
            if user.active_operation_mode is None or not was_completed:
                user.active_operation_mode = onboarding.operation_mode
                user.operation_mode_changed_at = now
            self.session.commit()
            self.session.refresh(onboarding)
        except Exception:
            self.session.rollback()
            raise
        return self._response(onboarding)

    def _active_strategy(self, strategy_id: str) -> Strategy:
        strategy = self.session.scalar(
            select(Strategy).where(Strategy.id == strategy_id, Strategy.is_active.is_(True))
        )
        if strategy is None:
            raise NotFoundError("STRATEGY_NOT_FOUND", "활성 투자 전략을 찾을 수 없습니다.")
        return strategy

    def _current_terms(self, strategy_id: str) -> list[Term]:
        codes = investment_term_codes(strategy_id)
        now = datetime.now(UTC)
        rows = self.session.scalars(
            select(Term)
            .where(Term.term_code.in_(codes), Term.effective_at <= now)
            .order_by(Term.term_code, Term.effective_at.desc(), Term.id.desc())
        )
        latest: dict[str, Term] = {}
        for term in rows:
            latest.setdefault(term.term_code, term)
        if set(latest) != set(codes) or any(not latest[code].is_required for code in codes):
            raise ServiceError(
                "TERMS_CATALOG_UNAVAILABLE",
                "현재 사용할 수 있는 투자 필수 약관이 준비되지 않았습니다.",
                503,
            )
        return [latest[code] for code in codes]

    def _has_current_agreements(self, user_id: int, strategy_id: str) -> bool:
        terms = self._current_terms(strategy_id)
        required_ids = {term.id for term in terms if term.is_required}
        agreed_ids = set(self.session.scalars(
            select(UserAgreement.term_id).where(
                UserAgreement.user_id == user_id,
                UserAgreement.term_id.in_(required_ids),
                UserAgreement.is_agreed.is_(True),
            )
        ))
        return required_ids == agreed_ids

    def _require_current_agreements(self, user_id: int, strategy_id: str) -> None:
        if not self._has_current_agreements(user_id, strategy_id):
            raise ServiceError("INVESTMENT_TERMS_NOT_AGREED", "최신 투자 필수 약관에 모두 동의해야 합니다.", 409)

    def _account_for_user(
        self,
        user_id: int,
        operation_mode: OperationMode,
        *,
        lock: bool = False,
    ) -> VirtualAccount | None:
        query = select(VirtualAccount).where(
            VirtualAccount.user_id == user_id,
            VirtualAccount.operation_mode == operation_mode,
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def _owned_onboarding_for_user(
        self,
        user_id: int,
        operation_mode: OperationMode,
    ) -> InvestmentOnboarding:
        onboarding = self.session.scalar(
            select(InvestmentOnboarding).where(
                InvestmentOnboarding.user_id == user_id,
                InvestmentOnboarding.operation_mode == operation_mode,
            )
        )
        if onboarding is None:
            raise NotFoundError("INVESTMENT_ONBOARDING_NOT_FOUND", "진행 중인 투자 시작 정보를 찾을 수 없습니다.")
        return onboarding

    def _deposit_for_key(self, account_id: UUID, idempotency_key: str) -> AccountDeposit | None:
        return self.session.scalar(
            select(AccountDeposit).where(
                AccountDeposit.account_id == account_id,
                AccountDeposit.idempotency_key == idempotency_key,
            )
        )

    @staticmethod
    def _required_deposit(investment_amount: Decimal, cash_balance: Decimal) -> Decimal:
        shortfall = max(Decimal("0.00"), Decimal(investment_amount) - Decimal(cash_balance))
        return shortfall.quantize(Decimal("0.01"))

    def _deposit_response(
        self,
        deposit: AccountDeposit,
        onboarding: InvestmentOnboarding,
    ) -> InvestmentDepositResponse:
        return InvestmentDepositResponse(
            deposit_id=deposit.id,
            amount=deposit.amount,
            balance_after=deposit.balance_after,
            required_deposit_amount=self._required_deposit(
                onboarding.investment_amount,
                deposit.balance_after,
            ),
            onboarding=self._response(onboarding),
        )

    def _owned_onboarding(self, user_id: int, onboarding_id: UUID, *, lock: bool = False) -> InvestmentOnboarding:
        query = select(InvestmentOnboarding).where(
            InvestmentOnboarding.id == onboarding_id,
            InvestmentOnboarding.user_id == user_id,
        )
        if lock:
            query = query.with_for_update()
        onboarding = self.session.scalar(query)
        if onboarding is None:
            raise NotFoundError("INVESTMENT_ONBOARDING_NOT_FOUND", "투자 시작 정보를 찾을 수 없습니다.")
        return onboarding

    @staticmethod
    def _ensure_verified_user(user: User) -> None:
        if user.phone_verified_at is None or user.email_verified_at is None:
            raise ServiceError("VERIFICATION_REQUIRED", "휴대폰과 이메일 인증이 필요합니다.", 403)

    def _response(self, onboarding: InvestmentOnboarding) -> InvestmentOnboardingResponse:
        terms_completed = self._has_current_agreements(onboarding.user_id, onboarding.strategy_id)
        account = self._account_for_user(onboarding.user_id, onboarding.operation_mode)
        if not terms_completed:
            status, next_step = "TERMS_PENDING", "TERMS"
        elif account is None:
            status, next_step = "ACCOUNT_PENDING", "ACCOUNT"
        elif onboarding.status == "COMPLETED" and onboarding.account_id == account.id:
            status, next_step = "COMPLETED", "PORTFOLIO"
        elif self._required_deposit(onboarding.investment_amount, account.cash_balance) > 0:
            status, next_step = "DEPOSIT_PENDING", "DEPOSIT"
        else:
            status, next_step = "READY", "CONFIRM"
        return InvestmentOnboardingResponse(
            id=onboarding.id,
            strategy_id=onboarding.strategy_id,
            investment_amount=onboarding.investment_amount,
            operation_mode=onboarding.operation_mode,
            status=status,
            account_id=account.id if account else None,
            terms_completed=terms_completed,
            account_exists=account is not None,
            next_step=next_step,
            completed_at=onboarding.completed_at if status == "COMPLETED" else None,
            created_at=onboarding.created_at,
            updated_at=onboarding.updated_at,
        )
