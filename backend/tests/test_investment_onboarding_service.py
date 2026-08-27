"""투자 약관 코드와 입력 경계값을 검증한다."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import ServiceError
from app.models import AccountDeposit, CashLedger, VirtualAccount
from app.schemas.api import InvestmentDepositRequest, InvestmentOnboardingCreateRequest, InvestmentOnboardingResponse
from app.services.investment_onboarding import InvestmentOnboardingService, investment_term_codes


class PrepareAccountSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, value) -> None:
        self.added.append(value)

    def flush(self) -> None:
        now = datetime.now(UTC)
        for value in self.added:
            if isinstance(value, VirtualAccount) and value.id is None:
                value.id = uuid4()
                value.created_at = now
                value.updated_at = now

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, _value) -> None:
        return None


class CompleteSession(PrepareAccountSession):
    def __init__(self, user) -> None:
        super().__init__()
        self.user = user
        self.lock_events = []

    def scalar(self, query):
        self.lock_events.append(("user", str(query)))
        return self.user


def ready_response(onboarding, account_id) -> InvestmentOnboardingResponse:
    return InvestmentOnboardingResponse(
        id=onboarding.id,
        strategy_id=onboarding.strategy_id,
        investment_amount=onboarding.investment_amount,
        operation_mode=onboarding.operation_mode,
        status="READY",
        account_id=account_id,
        terms_completed=True,
        account_exists=True,
        next_step="CONFIRM",
        completed_at=None,
        created_at=onboarding.created_at,
        updated_at=onboarding.updated_at,
    )


def deposit_pending_response(onboarding, account_id) -> InvestmentOnboardingResponse:
    return InvestmentOnboardingResponse(
        id=onboarding.id,
        strategy_id=onboarding.strategy_id,
        investment_amount=onboarding.investment_amount,
        operation_mode=onboarding.operation_mode,
        status="DEPOSIT_PENDING",
        account_id=account_id,
        terms_completed=True,
        account_exists=True,
        next_step="DEPOSIT",
        completed_at=None,
        created_at=onboarding.created_at,
        updated_at=onboarding.updated_at,
    )


def test_investment_term_codes_include_strategy_product_and_common_terms() -> None:
    assert investment_term_codes("low") == (
        "INVEST_PRODUCT_LOW",
        "INVEST_SERVICE",
        "INVEST_PRIVACY",
        "INVEST_LOSS_NOTICE",
    )


def test_product_term_code_rejects_strategy_id_that_exceeds_term_limit() -> None:
    with pytest.raises(ServiceError) as error:
        investment_term_codes("strategy-id-that-is-far-too-long")

    assert error.value.code == "INVALID_STRATEGY_ID"


@pytest.mark.parametrize("amount", [0, -1, 100_000_001])
def test_onboarding_request_rejects_invalid_investment_amount(amount: int) -> None:
    with pytest.raises(ValidationError):
        InvestmentOnboardingCreateRequest(
            strategy_id="low",
            investment_amount=amount,
            operation_mode="AUTO",
        )


@pytest.mark.parametrize(
    ("terms_completed", "cash_balance", "stored_status", "next_step"),
    [
        (False, None, "TERMS_PENDING", "TERMS"),
        (True, None, "ACCOUNT_PENDING", "ACCOUNT"),
        (True, Decimal("0"), "DEPOSIT_PENDING", "DEPOSIT"),
        (True, Decimal("1000000"), "READY", "CONFIRM"),
        (True, Decimal("1000000"), "COMPLETED", "PORTFOLIO"),
    ],
)
def test_response_derives_next_step_from_server_state(
    monkeypatch,
    terms_completed: bool,
    cash_balance: Decimal | None,
    stored_status: str,
    next_step: str,
) -> None:
    now = datetime.now(UTC)
    account_id = uuid4() if cash_balance is not None else None
    onboarding = SimpleNamespace(
        id=uuid4(),
        user_id=7,
        strategy_id="low",
        investment_amount=Decimal("1000000"),
        operation_mode="AUTO",
        status=stored_status,
        account_id=account_id,
        completed_at=now if stored_status == "COMPLETED" else None,
        created_at=now,
        updated_at=now,
    )
    service = InvestmentOnboardingService(SimpleNamespace())
    monkeypatch.setattr(service, "_has_current_agreements", lambda *_: terms_completed)
    monkeypatch.setattr(
        service,
        "_account_for_user",
        lambda *_args, **_kwargs: (
            SimpleNamespace(id=account_id, cash_balance=cash_balance)
            if cash_balance is not None
            else None
        ),
    )

    response = service._response(onboarding)

    assert response.next_step == next_step


def test_new_account_starts_empty_and_requires_exact_deposit(monkeypatch) -> None:
    now = datetime.now(UTC)
    onboarding = SimpleNamespace(
        id=uuid4(), user_id=7, strategy_id="low",
        investment_amount=Decimal("1000000"), operation_mode="AUTO",
        status="ACCOUNT_PENDING", account_id=None, completed_at=None,
        created_at=now, updated_at=now,
    )
    user = SimpleNamespace(id=7, email_verified_at=now)
    session = PrepareAccountSession()
    service = InvestmentOnboardingService(session)
    monkeypatch.setattr(service, "_owned_onboarding", lambda *_args, **_kwargs: onboarding)
    monkeypatch.setattr(service, "_require_current_agreements", lambda *_: None)
    monkeypatch.setattr(service, "_account_for_user", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_response", lambda value: deposit_pending_response(value, value.account_id))

    result = service.prepare_account(user, onboarding.id, "100만원 가상계좌")

    account = next(value for value in session.added if isinstance(value, VirtualAccount))
    assert result.created is True
    assert account.operation_mode == "AUTO"
    assert account.initial_cash == Decimal("0")
    assert account.cash_balance == Decimal("0")
    assert result.required_deposit_amount == Decimal("1000000")
    assert result.onboarding.next_step == "DEPOSIT"
    assert not any(isinstance(value, CashLedger) for value in session.added)
    assert session.commits == 1
    assert session.rollbacks == 0


def test_existing_account_keeps_balance_without_additional_deposit(monkeypatch) -> None:
    now = datetime.now(UTC)
    onboarding = SimpleNamespace(
        id=uuid4(), user_id=7, strategy_id="value",
        investment_amount=Decimal("500000"), operation_mode="SEMI_AUTO",
        status="ACCOUNT_PENDING", account_id=None, completed_at=None,
        created_at=now, updated_at=now,
    )
    user = SimpleNamespace(id=7, email_verified_at=now)
    account = VirtualAccount(
        id=uuid4(), user_id=7, account_name="기존 계좌",
        operation_mode="SEMI_AUTO",
        initial_cash=Decimal("1000000"), cash_balance=Decimal("750000"),
        status="ACTIVE", created_at=now, updated_at=now,
    )
    session = PrepareAccountSession()
    service = InvestmentOnboardingService(session)
    monkeypatch.setattr(service, "_owned_onboarding", lambda *_args, **_kwargs: onboarding)
    monkeypatch.setattr(service, "_require_current_agreements", lambda *_: None)
    monkeypatch.setattr(service, "_account_for_user", lambda *_args, **_kwargs: account)
    monkeypatch.setattr(service, "_response", lambda value: ready_response(value, account.id))

    result = service.prepare_account(user, onboarding.id, "변경하지 않을 이름")

    assert result.created is False
    assert result.account.initial_cash == Decimal("1000000")
    assert result.account.cash_balance == Decimal("750000")
    assert result.required_deposit_amount == Decimal("0")
    assert account.account_name == "기존 계좌"
    assert session.added == []
    assert session.commits == 1


def test_complete_activates_new_operation_mode(monkeypatch) -> None:
    now = datetime.now(UTC)
    user = SimpleNamespace(
        id=7,
        active_operation_mode="SEMI_AUTO",
        operation_mode_changed_at=now,
    )
    account = VirtualAccount(
        id=uuid4(), user_id=7, account_name="자동 계좌", operation_mode="AUTO",
        initial_cash=Decimal("1000000"), cash_balance=Decimal("1000000"),
        status="ACTIVE", created_at=now, updated_at=now,
    )
    onboarding = SimpleNamespace(
        id=uuid4(), user_id=7, strategy_id="low",
        investment_amount=Decimal("1000000"), operation_mode="AUTO",
        status="READY", account_id=account.id, completed_at=None,
        created_at=now, updated_at=now,
    )
    session = CompleteSession(user)
    service = InvestmentOnboardingService(session)
    def locked_onboarding(*_args, **_kwargs):
        session.lock_events.append(("onboarding", ""))
        return onboarding

    def locked_account(*_args, **_kwargs):
        session.lock_events.append(("account", ""))
        return account

    monkeypatch.setattr(service, "_owned_onboarding", locked_onboarding)
    monkeypatch.setattr(service, "_require_current_agreements", lambda *_: None)
    monkeypatch.setattr(service, "_account_for_user", locked_account)
    monkeypatch.setattr(service, "_active_strategy", lambda *_: SimpleNamespace())
    monkeypatch.setattr(service, "_response", lambda value: value)

    service.complete(7, onboarding.id)

    assert onboarding.status == "COMPLETED"
    assert account.selected_strategy_id == "low"
    assert user.active_operation_mode == "AUTO"
    assert user.operation_mode_changed_at >= now
    assert [event[0] for event in session.lock_events] == ["user", "onboarding", "account"]
    assert "FOR UPDATE" in session.lock_events[0][1]
    assert session.commits == 1


def test_complete_retry_does_not_override_later_mode_selection(monkeypatch) -> None:
    now = datetime.now(UTC)
    user = SimpleNamespace(
        id=7,
        active_operation_mode="SEMI_AUTO",
        operation_mode_changed_at=now,
    )
    account = VirtualAccount(
        id=uuid4(), user_id=7, account_name="자동 계좌", operation_mode="AUTO",
        initial_cash=Decimal("1000000"), cash_balance=Decimal("1000000"),
        status="ACTIVE", selected_strategy_id="low", created_at=now, updated_at=now,
    )
    onboarding = SimpleNamespace(
        id=uuid4(), user_id=7, strategy_id="low",
        investment_amount=Decimal("1000000"), operation_mode="AUTO",
        status="COMPLETED", account_id=account.id, completed_at=now,
        created_at=now, updated_at=now,
    )
    session = CompleteSession(user)
    service = InvestmentOnboardingService(session)
    monkeypatch.setattr(service, "_owned_onboarding", lambda *_args, **_kwargs: onboarding)
    monkeypatch.setattr(service, "_require_current_agreements", lambda *_: None)
    monkeypatch.setattr(service, "_account_for_user", lambda *_args, **_kwargs: account)
    monkeypatch.setattr(service, "_active_strategy", lambda *_: SimpleNamespace())
    monkeypatch.setattr(service, "_response", lambda value: value)

    service.complete(7, onboarding.id)

    assert user.active_operation_mode == "SEMI_AUTO"
    assert user.operation_mode_changed_at == now
    assert session.commits == 1


def test_exact_deposit_updates_account_ledger_and_onboarding_once(monkeypatch) -> None:
    now = datetime.now(UTC)
    account = VirtualAccount(
        id=uuid4(), user_id=7, account_name="자동 계좌", operation_mode="AUTO",
        initial_cash=Decimal("0"), cash_balance=Decimal("0"),
        status="ACTIVE", created_at=now, updated_at=now,
    )
    onboarding = SimpleNamespace(
        id=uuid4(), user_id=7, strategy_id="low",
        investment_amount=Decimal("1000000"), operation_mode="AUTO",
        status="DEPOSIT_PENDING", account_id=account.id, completed_at=None,
        created_at=now, updated_at=now,
    )
    session = PrepareAccountSession()
    service = InvestmentOnboardingService(session)
    monkeypatch.setattr(service, "_owned_onboarding", lambda *_args, **_kwargs: onboarding)
    monkeypatch.setattr(service, "_require_current_agreements", lambda *_: None)
    monkeypatch.setattr(service, "_account_for_user", lambda *_args, **_kwargs: account)
    monkeypatch.setattr(service, "_deposit_for_key", lambda *_: None)
    monkeypatch.setattr(service, "_response", lambda value: ready_response(value, account.id))

    result = service.deposit(
        7,
        onboarding.id,
        InvestmentDepositRequest(amount=1_000_000, idempotency_key="deposit-once-1"),
    )

    deposit = next(value for value in session.added if isinstance(value, AccountDeposit))
    ledger = next(value for value in session.added if isinstance(value, CashLedger))
    assert account.initial_cash == Decimal("1000000")
    assert account.cash_balance == Decimal("1000000")
    assert account.invested_principal == Decimal("1000000.00")
    assert onboarding.status == "READY"
    assert deposit.amount == ledger.amount == Decimal("1000000")
    assert deposit.balance_after == ledger.balance_after == Decimal("1000000")
    assert ledger.transaction_type == "DEPOSIT"
    assert ledger.reference_id == str(deposit.id)
    assert result.required_deposit_amount == Decimal("0")
    assert str(result.required_deposit_amount) == "0.00"
    assert result.onboarding.next_step == "CONFIRM"
    assert session.commits == 1


def test_deposit_rejects_amount_other_than_current_shortfall(monkeypatch) -> None:
    now = datetime.now(UTC)
    account = VirtualAccount(
        id=uuid4(), user_id=7, account_name="반자동 계좌", operation_mode="SEMI_AUTO",
        initial_cash=Decimal("1000000"), cash_balance=Decimal("250000"),
        status="ACTIVE", created_at=now, updated_at=now,
    )
    onboarding = SimpleNamespace(
        id=uuid4(), user_id=7, strategy_id="value",
        investment_amount=Decimal("1000000"), operation_mode="SEMI_AUTO",
        status="DEPOSIT_PENDING", account_id=account.id, completed_at=None,
        created_at=now, updated_at=now,
    )
    session = PrepareAccountSession()
    service = InvestmentOnboardingService(session)
    monkeypatch.setattr(service, "_owned_onboarding", lambda *_args, **_kwargs: onboarding)
    monkeypatch.setattr(service, "_require_current_agreements", lambda *_: None)
    monkeypatch.setattr(service, "_account_for_user", lambda *_args, **_kwargs: account)
    monkeypatch.setattr(service, "_deposit_for_key", lambda *_: None)

    with pytest.raises(ServiceError) as error:
        service.deposit(
            7,
            onboarding.id,
            InvestmentDepositRequest(amount=700_000, idempotency_key="wrong-amount-1"),
        )

    assert error.value.code == "INVALID_DEPOSIT_AMOUNT"
    assert account.cash_balance == Decimal("250000")
    assert session.added == []
    assert session.commits == 0


def test_deposit_retry_with_same_key_returns_existing_result(monkeypatch) -> None:
    now = datetime.now(UTC)
    account = VirtualAccount(
        id=uuid4(), user_id=7, account_name="자동 계좌", operation_mode="AUTO",
        initial_cash=Decimal("1000000"), cash_balance=Decimal("1000000"),
        status="ACTIVE", created_at=now, updated_at=now,
    )
    onboarding = SimpleNamespace(
        id=uuid4(), user_id=7, strategy_id="low",
        investment_amount=Decimal("1000000"), operation_mode="AUTO",
        status="READY", account_id=account.id, completed_at=None,
        created_at=now, updated_at=now,
    )
    existing = AccountDeposit(
        id=uuid4(), account_id=account.id, onboarding_id=onboarding.id,
        amount=Decimal("1000000"), balance_after=Decimal("1000000"),
        status="COMPLETED", idempotency_key="same-deposit-1",
        created_at=now, completed_at=now,
    )
    session = PrepareAccountSession()
    service = InvestmentOnboardingService(session)
    monkeypatch.setattr(service, "_owned_onboarding", lambda *_args, **_kwargs: onboarding)
    monkeypatch.setattr(service, "_require_current_agreements", lambda *_: None)
    monkeypatch.setattr(service, "_account_for_user", lambda *_args, **_kwargs: account)
    monkeypatch.setattr(service, "_deposit_for_key", lambda *_: existing)
    monkeypatch.setattr(service, "_response", lambda value: ready_response(value, account.id))

    result = service.deposit(
        7,
        onboarding.id,
        InvestmentDepositRequest(amount=1_000_000, idempotency_key="same-deposit-1"),
    )

    assert result.deposit_id == existing.id
    assert result.balance_after == Decimal("1000000")
    assert session.added == []
    assert session.commits == 0
