from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes.strategy_recommendations import get_strategy_recommendation_service
from app.main import app
from app.schemas.api import StrategyRecommendationResponse


ASSESSMENT_ID = uuid4()


class FakeService:
    def __init__(self) -> None:
        self.calls = []

    async def recommend(self, user_id, assessment_id):
        self.calls.append((user_id, assessment_id))
        return response()

    def latest(self, user_id):
        self.calls.append((user_id, "latest"))
        return response()


def response() -> StrategyRecommendationResponse:
    return StrategyRecommendationResponse(
        recommendation_id=uuid4(),
        assessment_id=ASSESSMENT_ID,
        primary={
            "strategy_id": "value", "rank": 1, "score": 0.84, "match_level": "BEST",
            "reason": "균형 성향과 맞습니다.", "caution": "회복에 시간이 필요합니다.",
        },
        alternatives=[
            {
                "strategy_id": "low", "rank": 2, "score": 0.73, "match_level": "GOOD",
                "reason": "안정성 선호와 맞습니다.", "caution": "상승장에서 뒤처질 수 있습니다.",
            }
        ],
        model_version="recommendation-v1",
        dataset_version="financial-8y-v1",
        created_at=datetime(2026, 8, 24, tzinfo=UTC),
    )


def install_overrides(service: FakeService) -> None:
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_strategy_recommendation_service] = lambda: service


def test_create_recommendation_passes_authenticated_owner_and_assessment() -> None:
    service = FakeService()
    install_overrides(service)
    try:
        result = TestClient(app).post(
            "/api/v1/strategy-recommendations",
            json={"assessment_id": str(ASSESSMENT_ID)},
        )
    finally:
        app.dependency_overrides.clear()

    assert result.status_code == 201
    assert result.json()["primary"]["strategy_id"] == "value"
    assert result.json()["dataset_version"] == "financial-8y-v1"
    assert service.calls == [(7, ASSESSMENT_ID)]


def test_latest_recommendation_uses_authenticated_user() -> None:
    service = FakeService()
    install_overrides(service)
    try:
        result = TestClient(app).get("/api/v1/strategy-recommendations/me/latest")
    finally:
        app.dependency_overrides.clear()

    assert result.status_code == 200
    assert service.calls == [(7, "latest")]


def test_create_recommendation_requires_authentication() -> None:
    result = TestClient(app).post(
        "/api/v1/strategy-recommendations",
        json={"assessment_id": str(ASSESSMENT_ID)},
    )
    assert result.status_code == 401
    assert result.json()["code"] == "AUTHENTICATION_REQUIRED"
