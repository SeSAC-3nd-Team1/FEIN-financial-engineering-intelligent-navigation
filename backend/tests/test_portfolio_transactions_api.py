"""포트폴리오 거래내역 API의 인증과 query 계약을 검증한다."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes.portfolio import get_transaction_history_service
from app.main import app


ACCOUNT_ID = uuid4()


class FakeTransactionHistoryService:
    def __init__(self) -> None:
        self.calls = []

    def list(self, user_id, account_id, *, limit, cursor):
        self.calls.append((user_id, account_id, limit, cursor))
        return {
            "account_id": account_id,
            "items": [{
                "id": 1,
                "order_id": uuid4(),
                "stock_code": "005930",
                "stock_name": "삼성전자",
                "side": "BUY",
                "quantity": "1.25",
                "execution_price": "70000",
                "transaction_amount": "87500.00",
                "executed_at": datetime(2026, 8, 25, tzinfo=UTC),
            }],
            "next_cursor": None,
            "has_more": False,
        }


def install(service: FakeTransactionHistoryService) -> None:
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_transaction_history_service] = lambda: service


def test_portfolio_transactions_passes_limit_and_cursor() -> None:
    service = FakeTransactionHistoryService()
    install(service)
    try:
        response = TestClient(app).get(
            f"/api/v1/portfolio/transactions?account_id={ACCOUNT_ID}&limit=3&cursor=next-page"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["transaction_amount"] == "87500.00"
    assert service.calls == [(7, ACCOUNT_ID, 3, "next-page")]


def test_portfolio_transactions_rejects_limit_over_100() -> None:
    service = FakeTransactionHistoryService()
    install(service)
    try:
        response = TestClient(app).get(
            f"/api/v1/portfolio/transactions?account_id={ACCOUNT_ID}&limit=101"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert service.calls == []


def test_portfolio_transactions_requires_authentication() -> None:
    response = TestClient(app).get(
        f"/api/v1/portfolio/transactions?account_id={ACCOUNT_ID}"
    )

    assert response.status_code == 401
