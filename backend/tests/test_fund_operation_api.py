"""내부 가상계좌 자금 API의 인증·요청 전달·응답 계약을 검증한다."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes.accounts import get_fund_operation_service
from app.main import app


ACCOUNT_ID = uuid4()
OPERATION_ID = uuid4()
NOW = datetime(2026, 8, 27, tzinfo=UTC)


class FakeFundService:
    def __init__(self) -> None:
        self.calls = []

    @staticmethod
    def _summary():
        return {
            "account_id": ACCOUNT_ID,
            "settlement_mode": "VIRTUAL",
            "invested_principal": "1000000.00",
            "cash_balance": "100000.00",
            "position_evaluation_amount": "900000.00",
            "total_assets": "1000000.00",
            "valuation_profit": "0.00",
            "return_rate": "0.00",
            "withdrawable_amount": "1000000.00",
            "valuation_as_of": NOW,
        }

    def summary(self, user_id, account_id):
        self.calls.append(("summary", user_id, account_id))
        return self._summary()

    def add_investment(self, user_id, account_id, payload):
        self.calls.append(("add", user_id, account_id, payload))
        return self._operation("ADDITIONAL_INVESTMENT", payload.amount)

    def withdraw(self, user_id, account_id, payload):
        self.calls.append(("withdraw", user_id, account_id, payload))
        return self._operation("WITHDRAWAL", payload.amount)

    def _operation(self, operation_type, amount):
        return {
            "operation_id": OPERATION_ID,
            "type": operation_type,
            "status": "COMPLETED",
            "settlement_mode": "VIRTUAL",
            "requested_amount": amount,
            "executed_amount": amount,
            "principal_before": "1000000.00",
            "principal_after": "1000000.00",
            "portfolio": self._summary(),
            "trades": [],
        }


def install(service: FakeFundService) -> None:
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_fund_operation_service] = lambda: service


def test_virtual_fund_endpoints_use_authenticated_account_owner() -> None:
    service = FakeFundService()
    install(service)
    try:
        client = TestClient(app)
        summary = client.get(f"/api/v1/accounts/{ACCOUNT_ID}/funds")
        added = client.post(
            f"/api/v1/accounts/{ACCOUNT_ID}/additional-investments",
            json={"amount": 100000, "idempotency_key": "add-api-0001"},
        )
        withdrawn = client.post(
            f"/api/v1/accounts/{ACCOUNT_ID}/withdrawals",
            json={"amount": 50000, "idempotency_key": "withdraw-api-0001"},
        )
    finally:
        app.dependency_overrides.clear()

    assert summary.status_code == 200
    assert summary.json()["settlement_mode"] == "VIRTUAL"
    assert added.status_code == 201
    assert added.json()["type"] == "ADDITIONAL_INVESTMENT"
    assert withdrawn.status_code == 201
    assert withdrawn.json()["type"] == "WITHDRAWAL"
    assert [call[0] for call in service.calls] == ["summary", "add", "withdraw"]


def test_virtual_fund_request_rejects_out_of_policy_amount() -> None:
    service = FakeFundService()
    install(service)
    try:
        response = TestClient(app).post(
            f"/api/v1/accounts/{ACCOUNT_ID}/withdrawals",
            json={"amount": 0, "idempotency_key": "withdraw-api-0002"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert service.calls == []
