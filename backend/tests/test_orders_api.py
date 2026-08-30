"""주문/체결 API의 종목명 enrichment 계약을 검증한다."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes import orders as orders_route
from app.db.session import get_session
from app.main import app


ACCOUNT_ID = uuid4()


class FakeSession:
    def execute(self, statement):
        execution = SimpleNamespace(
            id=17,
            order_id=uuid4(),
            stock_code="005930",
            side="BUY",
            quantity="1.25000000",
            execution_price="70000.0000",
            executed_at=datetime(2026, 8, 25, tzinfo=UTC),
        )
        return [(execution, "삼성전자")]


def test_executions_includes_market_stock_name() -> None:
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_session] = lambda: FakeSession()
    try:
        with patch.object(
            orders_route.TradingRepository,
            "owned_account",
            return_value=True,
        ):
            response = TestClient(app).get(
                f"/api/v1/executions?account_id={ACCOUNT_ID}"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["stock_code"] == "005930"
    assert response.json()[0]["stock_name"] == "삼성전자"
