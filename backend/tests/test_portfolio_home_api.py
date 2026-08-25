"""포트폴리오 홈 통합 API의 인증과 query 계약을 검증한다."""

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes.portfolio import get_portfolio_service
from app.main import app


ACCOUNT_ID = uuid4()


class FakePortfolioService:
    def __init__(self) -> None:
        self.calls = []

    def home(self, user_id, account_id, period, sort_by, order):
        self.calls.append((user_id, account_id, period, sort_by, order))
        return {
            "account": {
                "id": account_id,
                "account_name": "나의 가상 투자계좌",
                "operation_mode": "SEMI_AUTO",
                "status": "ACTIVE",
                "selected_strategy_id": "low",
            },
            "summary": {
                "cash_balance": 1000000,
                "total_purchase_amount": 0,
                "total_evaluation_amount": 0,
                "total_assets": 1000000,
                "unrealized_profit": 0,
                "realized_profit": 0,
                "return_rate": 0,
                "today_profit": None,
                "top_contributor": None,
            },
            "trend": {
                "account_id": account_id,
                "period": period,
                "benchmark_name": "KOSPI",
                "items": [],
            },
            "allocations": [
                {"type": "CASH", "stock_code": None, "name": "현금", "amount": 1000000, "weight": 100}
            ],
            "positions": [],
            "contributions": [],
            "strategy_targets_available": False,
            "rebalancing_proposals": [],
            "valuation_as_of": None,
            "price_sources": [],
        }


def test_portfolio_home_passes_default_and_custom_query_options() -> None:
    service = FakePortfolioService()
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_portfolio_service] = lambda: service
    try:
        client = TestClient(app)
        default_response = client.get(f"/api/v1/portfolio/home?account_id={ACCOUNT_ID}")
        custom_response = client.get(
            f"/api/v1/portfolio/home?account_id={ACCOUNT_ID}"
            "&period=1Y&sort=stock_name&order=asc"
        )
    finally:
        app.dependency_overrides.clear()

    assert default_response.status_code == 200
    assert default_response.json()["allocations"][0]["type"] == "CASH"
    assert custom_response.status_code == 200
    assert service.calls == [
        (7, ACCOUNT_ID, "3M", "weight", "desc"),
        (7, ACCOUNT_ID, "1Y", "stock_name", "asc"),
    ]


def test_portfolio_home_rejects_unsupported_sort_column() -> None:
    service = FakePortfolioService()
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_portfolio_service] = lambda: service
    try:
        response = TestClient(app).get(
            f"/api/v1/portfolio/home?account_id={ACCOUNT_ID}&sort=unknown"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert service.calls == []


def test_portfolio_home_requires_authentication() -> None:
    response = TestClient(app).get(f"/api/v1/portfolio/home?account_id={ACCOUNT_ID}")

    assert response.status_code == 401
