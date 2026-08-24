"""투자 약관 코드와 입력 경계값을 검증한다."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import ServiceError
from app.models import CashLedger, VirtualAccount
from app.schemas.api import InvestmentOnboardingCreateRequest, InvestmentOnboardingResponse
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
    ("terms_completed", "has_account", "stored_status", "next_step"),
    [
        (False, False, "TERMS_PENDING", "TERMS"),
        (True, False, "ACCOUNT_PENDING", "ACCOUNT"),
        (True, True, "READY", "CONFIRM"),
        (True, True, "COMPLETED", "PORTFOLIO"),
    ],
)
def test_response_derives_next_step_from_server_state(
    monkeypatch,
    terms_completed: bool,
    has_account: bool,
    stored_status: str,
    next_step: str,
) -> None:
    now = datetime.now(UTC)
    account_id = uuid4() if has_account else None
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
        lambda *_args, **_kwargs: SimpleNamespace(id=account_id) if has_account else None,
    )

    response = service._response(onboarding)

    assert response.next_step == next_step


def test_new_account_uses_selected_investment_amount_for_cash_and_ledger(monkeypatch) -> None:
    now = datetime.now(UTC)
    onboarding = SimpleNamespace(
        id=uuid4(), user_id=7, strategy_id="low",
        investment_amount=Decimal("1000000"), operation_mode="AUTO",
        status="ACCOUNT_PENDING", account_id=None, completed_at=None,
        created_at=now, updated_at=now,
    )
    user = SimpleNamespace(id=7, phone_verified_at=now, email_verified_at=now)
    session = PrepareAccountSession()
    service = InvestmentOnboardingService(session)
    monkeypatch.setattr(service, "_owned_onboarding", lambda *_args, **_kwargs: onboarding)
    monkeypatch.setattr(service, "_require_current_agreements", lambda *_: None)
    monkeypatch.setattr(service, "_account_for_user", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_response", lambda value: ready_response(value, value.account_id))

    result = service.prepare_account(user, onboarding.id, "100만원 가상계좌")

    account = next(value for value in session.added if isinstance(value, VirtualAccount))
    ledger = next(value for value in session.added if isinstance(value, CashLedger))
    assert result.created is True
    assert account.initial_cash == Decimal("1000000")
    assert account.cash_balance == Decimal("1000000")
    assert ledger.amount == Decimal("1000000")
    assert ledger.balance_after == Decimal("1000000")
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
    user = SimpleNamespace(id=7, phone_verified_at=now, email_verified_at=now)
    account = VirtualAccount(
        id=uuid4(), user_id=7, account_name="기존 계좌",
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
    assert account.account_name == "기존 계좌"
    assert session.added == []
    assert session.commits == 1
