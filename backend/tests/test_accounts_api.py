"""활성 운용방식 전환 API의 인증과 요청 계약을 검증한다."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes.accounts import get_account_service
from app.main import app


NOW = datetime(2026, 8, 25, tzinfo=UTC)
ACCOUNT_ID = uuid4()


class FakeAccountService:
    def __init__(self) -> None:
        self.calls = []

    def switch_active_operation_mode(self, user_id, operation_mode):
        self.calls.append((user_id, operation_mode))
        return {
            "previous_operation_mode": "SEMI_AUTO",
            "operation_mode": operation_mode,
            "changed": True,
            "changed_at": NOW,
            "account": {
                "id": ACCOUNT_ID,
                "account_name": "자동 계좌",
                "operation_mode": "AUTO",
                "initial_cash": "1000000",
                "cash_balance": "750000",
                "status": "ACTIVE",
                "selected_strategy_id": "low",
                "created_at": NOW,
            },
            "notice": {
                "code": "OPERATION_MODE_CHANGED",
                "title": "운용방식이 변경됐어요",
                "message": "계좌를 전환했어요.",
            },
        }


def install(service: FakeAccountService) -> None:
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_account_service] = lambda: service


def test_switch_active_operation_mode_passes_authenticated_user() -> None:
    service = FakeAccountService()
    install(service)
    try:
        response = TestClient(app).put(
            "/api/v1/accounts/me/active-operation-mode",
            json={"operation_mode": "AUTO"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["previous_operation_mode"] == "SEMI_AUTO"
    assert response.json()["operation_mode"] == "AUTO"
    assert response.json()["notice"]["code"] == "OPERATION_MODE_CHANGED"
    assert service.calls == [(7, "AUTO")]


def test_switch_active_operation_mode_rejects_unknown_mode() -> None:
    service = FakeAccountService()
    install(service)
    try:
        response = TestClient(app).put(
            "/api/v1/accounts/me/active-operation-mode",
            json={"operation_mode": "MANUAL"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert service.calls == []


def test_switch_active_operation_mode_requires_authentication() -> None:
    response = TestClient(app).put(
        "/api/v1/accounts/me/active-operation-mode",
        json={"operation_mode": "AUTO"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
