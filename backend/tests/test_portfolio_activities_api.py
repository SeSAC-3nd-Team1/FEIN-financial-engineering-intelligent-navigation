"""매매·가상 입출금 통합 활동 API 계약을 검증한다."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes.portfolio import get_activity_history_service
from app.main import app


ACCOUNT_ID = uuid4()


class FakeActivityService:
    def __init__(self) -> None:
        self.calls = []

    def list(self, user_id, account_id, *, limit, cursor):
        self.calls.append((user_id, account_id, limit, cursor))
        return {
            "account_id": account_id,
            "settlement_mode": "VIRTUAL",
            "items": [
                {
                    "id": 10,
                    "type": "WITHDRAWAL",
                    "cash_amount": "-50000.00",
                    "transaction_amount": "50000.00",
                    "balance_after": "100000.00",
                    "reference_id": str(uuid4()),
                    "occurred_at": datetime(2026, 8, 27, tzinfo=UTC),
                }
            ],
            "next_cursor": None,
            "has_more": False,
        }


def test_portfolio_activities_returns_virtual_cash_timeline() -> None:
    service = FakeActivityService()
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_activity_history_service] = lambda: service
    try:
        response = TestClient(app).get(
            f"/api/v1/portfolio/activities?account_id={ACCOUNT_ID}&limit=10"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["settlement_mode"] == "VIRTUAL"
    assert response.json()["items"][0]["type"] == "WITHDRAWAL"
    assert service.calls == [(7, ACCOUNT_ID, 10, None)]
