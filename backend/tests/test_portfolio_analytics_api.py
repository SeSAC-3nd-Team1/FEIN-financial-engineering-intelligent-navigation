"""포트폴리오 feature와 판단 이력 API 계약을 검증한다."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes.portfolio import get_portfolio_analytics_service
from app.main import app
from app.schemas.api import (
    RebalancingDecisionHistoryResponse,
    RebalancingDecisionResponse,
    StockEvaluationResponse,
)


ACCOUNT_ID = uuid4()


def decision_response() -> RebalancingDecisionResponse:
    return RebalancingDecisionResponse(
        id=uuid4(), account_id=ACCOUNT_ID, strategy_id="low", stock_code="005930",
        stock_name="삼성전자", action="SELL", current_weight=Decimal("20"),
        target_weight=Decimal("15"), weight_diff=Decimal("5"),
        recommended_amount=Decimal("50000"), decision="HELD",
        baseline_snapshot_date=date(2026, 8, 25), actual_portfolio_return_rate=None,
        outcome_as_of=None, created_at=datetime(2026, 8, 25, tzinfo=UTC),
    )


class FakeService:
    def __init__(self) -> None:
        self.calls = []

    def stock_evaluation(self, user_id, account_id, stock_code):
        self.calls.append(("evaluation", user_id, account_id, stock_code))
        return StockEvaluationResponse(
            account_id=account_id, stock_code=stock_code, stock_name="삼성전자",
            as_of=date(2026, 8, 25), target_weight=Decimal("15"),
            role_summary="안정성이 높습니다.",
            axes=[{"key": "stability", "label": "안정성", "score": 80, "status": "AVAILABLE", "basis": "KRX"}],
            sources=["KRX"],
        )

    def record_decision(self, user_id, request):
        self.calls.append(("record", user_id, request))
        return decision_response()

    def decision_history(self, user_id, account_id):
        self.calls.append(("history", user_id, account_id))
        return RebalancingDecisionHistoryResponse(
            account_id=account_id, proposed=1, accepted=0, held=1,
            accepted_average_portfolio_return=None, held_average_portfolio_return=None,
            items=[decision_response()],
        )


def install(service: FakeService) -> None:
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_portfolio_analytics_service] = lambda: service


def test_stock_evaluation_and_decision_endpoints_use_authenticated_owner() -> None:
    service = FakeService()
    install(service)
    try:
        client = TestClient(app)
        evaluation = client.get(
            f"/api/v1/portfolio/stock-evaluation?account_id={ACCOUNT_ID}&stock_code=005930"
        )
        created = client.post("/api/v1/portfolio/decisions", json={
            "account_id": str(ACCOUNT_ID), "stock_code": "005930",
            "decision": "HELD", "idempotency_key": "decision-1",
        })
        history = client.get(f"/api/v1/portfolio/decisions?account_id={ACCOUNT_ID}")
    finally:
        app.dependency_overrides.clear()

    assert evaluation.status_code == 200
    assert evaluation.json()["feature_version"] == "stock-feature-v1"
    assert created.status_code == 201
    assert created.json()["decision"] == "HELD"
    assert history.status_code == 200
    assert history.json()["proposed"] == 1
    assert [call[0] for call in service.calls] == ["evaluation", "record", "history"]


def test_portfolio_analytics_endpoints_require_authentication() -> None:
    response = TestClient(app).get(
        f"/api/v1/portfolio/stock-evaluation?account_id={ACCOUNT_ID}&stock_code=005930"
    )

    assert response.status_code == 401
