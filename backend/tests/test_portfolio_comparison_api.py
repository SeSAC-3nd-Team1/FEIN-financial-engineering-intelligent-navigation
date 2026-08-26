"""투자 비교 endpoint의 인증과 프론트 응답 계약을 검증한다."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes.portfolio import get_portfolio_comparison_service
from app.main import app
from app.schemas.api import PortfolioComparisonResponse


class FakeService:
    def __init__(self) -> None:
        self.calls = []

    async def compare(self, user_id, period):
        self.calls.append((user_id, period))
        return PortfolioComparisonResponse(
            comparison_status="AVAILABLE",
            period=period,
            baseline_date=date(2026, 8, 20),
            as_of=date(2026, 8, 25),
            observation_count=2,
            accounts={
                "ai_auto": {
                    "account_id": uuid4(), "account_name": "AI 자동투자",
                    "operation_mode": "AUTO", "strategy_id": "low",
                    "baseline_assets": "1000000", "current_assets": "1100000",
                    "return_rate": "10.00",
                },
                "my_investment": {
                    "account_id": uuid4(), "account_name": "내 투자",
                    "operation_mode": "SEMI_AUTO", "strategy_id": "balanced",
                    "baseline_assets": "1000000", "current_assets": "1050000",
                    "return_rate": "5.00",
                },
            },
            metrics={"return_rate_gap": "5.00", "asset_gap": "50000", "leader": "AI_AUTO"},
            series=[{
                "date": date(2026, 8, 20), "ai_auto_return_rate": Decimal("0"),
                "my_investment_return_rate": Decimal("0"), "return_rate_gap": Decimal("0"),
            }],
            ai_analysis={
                "status": "AVAILABLE", "headline": "AI 자동투자가 앞섰습니다.",
                "summary": "동일 기간 수익률을 비교했습니다.", "key_points": ["격차 5.00%p"],
                "caution": "과거 가상투자 결과입니다.",
                "model_version": "portfolio-comparison-v1", "generated_at": None,
            },
        )


def test_comparison_endpoint_uses_authenticated_user_and_period() -> None:
    service = FakeService()
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_portfolio_comparison_service] = lambda: service
    try:
        response = TestClient(app).get("/api/v1/portfolio/comparison?period=1Y")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["calculation_version"] == "portfolio-comparison-v1"
    assert response.json()["metrics"]["leader"] == "AI_AUTO"
    assert response.json()["ai_analysis"]["status"] == "AVAILABLE"
    assert service.calls == [(7, "1Y")]


def test_comparison_endpoint_requires_authentication() -> None:
    response = TestClient(app).get("/api/v1/portfolio/comparison")

    assert response.status_code == 401
