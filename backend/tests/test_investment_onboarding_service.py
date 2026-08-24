"""투자 약관 코드와 입력 경계값을 검증한다."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import ServiceError
from app.schemas.api import InvestmentOnboardingCreateRequest
from app.services.investment_onboarding import InvestmentOnboardingService, investment_term_codes


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
