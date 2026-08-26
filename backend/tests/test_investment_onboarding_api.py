"""투자 시작 API가 인증 사용자와 요청 정보를 서비스에 전달하는지 검증한다."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes.investment import get_investment_onboarding_service
from app.main import app
from app.schemas.api import (
    AccountResponse,
    InvestmentAccountPrepareResponse,
    InvestmentDepositResponse,
    InvestmentOnboardingResponse,
    InvestmentTermResponse,
)


ONBOARDING_ID = uuid4()
ACCOUNT_ID = uuid4()
NOW = datetime(2026, 8, 24, tzinfo=UTC)


def onboarding_response(**overrides) -> InvestmentOnboardingResponse:
    values = {
        "id": ONBOARDING_ID,
        "strategy_id": "low",
        "investment_amount": Decimal("1000000"),
        "operation_mode": "AUTO",
        "status": "TERMS_PENDING",
        "account_id": None,
        "terms_completed": False,
        "account_exists": False,
        "next_step": "TERMS",
        "completed_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return InvestmentOnboardingResponse(**values)


class FakeService:
    def __init__(self) -> None:
        self.calls = []

    def terms(self, strategy_id):
        self.calls.append(("terms", strategy_id))
        return [
            InvestmentTermResponse(
                term_code="INVEST_PRODUCT_LOW",
                version="dev-test",
                title="저변동성 전략 상품설명서",
                is_required=True,
            )
        ]

    def create_or_update(self, user, payload):
        self.calls.append(("create", user.id, payload))
        return onboarding_response()

    def current(self, user_id, operation_mode):
        self.calls.append(("current", user_id, operation_mode))
        return onboarding_response()

    def currents(self, user_id):
        self.calls.append(("currents", user_id))
        return [onboarding_response()]

    def agree(self, user_id, onboarding_id, payload, *, agreed_ip, user_agent):
        self.calls.append(("agree", user_id, onboarding_id, payload, agreed_ip, user_agent))
        return onboarding_response(status="ACCOUNT_PENDING", terms_completed=True, next_step="ACCOUNT")

    def prepare_account(self, user, onboarding_id, account_name):
        self.calls.append(("account", user.id, onboarding_id, account_name))
        account = AccountResponse(
            id=ACCOUNT_ID,
            account_name=account_name,
            operation_mode="AUTO",
            initial_cash=Decimal("0"),
            cash_balance=Decimal("0"),
            status="ACTIVE",
            selected_strategy_id=None,
            created_at=NOW,
        )
        return InvestmentAccountPrepareResponse(
            account=account,
            created=True,
            required_deposit_amount=Decimal("1000000"),
            onboarding=onboarding_response(
                status="DEPOSIT_PENDING",
                account_id=ACCOUNT_ID,
                terms_completed=True,
                account_exists=True,
                next_step="DEPOSIT",
            ),
        )

    def deposit(self, user_id, onboarding_id, payload):
        self.calls.append(("deposit", user_id, onboarding_id, payload))
        return InvestmentDepositResponse(
            deposit_id=uuid4(),
            amount=payload.amount,
            balance_after=payload.amount,
            required_deposit_amount=Decimal("0"),
            onboarding=onboarding_response(
                status="READY",
                account_id=ACCOUNT_ID,
                terms_completed=True,
                account_exists=True,
                next_step="CONFIRM",
            ),
        )

    def complete(self, user_id, onboarding_id):
        self.calls.append(("complete", user_id, onboarding_id))
        return onboarding_response(
            status="COMPLETED",
            account_id=ACCOUNT_ID,
            terms_completed=True,
            account_exists=True,
            next_step="PORTFOLIO",
            completed_at=NOW,
        )


def install_overrides(service: FakeService) -> None:
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(
        id=7,
        email_verified_at=NOW,
    )
    app.dependency_overrides[get_investment_onboarding_service] = lambda: service


def test_create_onboarding_passes_authenticated_user_and_selection() -> None:
    service = FakeService()
    install_overrides(service)
    try:
        response = TestClient(app).post("/api/v1/investment/onboardings", json={
            "strategy_id": "low",
            "investment_amount": 1_000_000,
            "operation_mode": "AUTO",
        })
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["next_step"] == "TERMS"
    _, user_id, payload = service.calls[0]
    assert user_id == 7
    assert payload.investment_amount == Decimal("1000000")


def test_agreement_passes_request_audit_metadata() -> None:
    service = FakeService()
    install_overrides(service)
    try:
        response = TestClient(app).post(
            f"/api/v1/investment/onboardings/{ONBOARDING_ID}/agreements",
            headers={"user-agent": "pytest-agent"},
            json={"agreements": [{
                "term_code": "INVEST_PRODUCT_LOW",
                "version": "dev-test",
                "agreed": True,
            }]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["next_step"] == "ACCOUNT"
    assert service.calls[0][1:3] == (7, ONBOARDING_ID)
    assert service.calls[0][-2] is None
    assert service.calls[0][-1] == "pytest-agent"


def test_prepare_and_complete_account_flow() -> None:
    service = FakeService()
    install_overrides(service)
    client = TestClient(app)
    try:
        prepared = client.post(
            f"/api/v1/investment/onboardings/{ONBOARDING_ID}/account",
            json={"account_name": "테스트 가상계좌"},
        )
        deposited = client.post(
            f"/api/v1/investment/onboardings/{ONBOARDING_ID}/deposit",
            json={"amount": 1_000_000, "idempotency_key": "api-deposit-once"},
        )
        completed = client.post(
            f"/api/v1/investment/onboardings/{ONBOARDING_ID}/complete"
        )
    finally:
        app.dependency_overrides.clear()

    assert prepared.status_code == 200
    assert prepared.json()["created"] is True
    assert prepared.json()["account"]["operation_mode"] == "AUTO"
    assert prepared.json()["account"]["initial_cash"] == "0"
    assert prepared.json()["account"]["cash_balance"] == "0"
    assert prepared.json()["required_deposit_amount"] == "1000000"
    assert prepared.json()["onboarding"]["next_step"] == "DEPOSIT"
    assert deposited.status_code == 200
    assert deposited.json()["balance_after"] == "1000000"
    assert deposited.json()["required_deposit_amount"] == "0"
    assert deposited.json()["onboarding"]["next_step"] == "CONFIRM"
    assert completed.status_code == 200
    assert completed.json()["next_step"] == "PORTFOLIO"


def test_current_onboarding_passes_operation_mode() -> None:
    service = FakeService()
    install_overrides(service)
    try:
        response = TestClient(app).get(
            "/api/v1/investment/onboardings/me/current?operation_mode=AUTO"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert service.calls == [("current", 7, "AUTO")]


def test_investment_onboarding_requires_authentication() -> None:
    response = TestClient(app).get("/api/v1/investment/onboardings/me/current")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
