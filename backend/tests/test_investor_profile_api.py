from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes.investor_profile import get_investor_profile_service
from app.core.errors import ServiceError
from app.main import app
from app.schemas.api import InvestorProfileResponse


PAYLOAD = {
    "questionnaire_version": "v1",
    "answers": [
        {"question_id": "investment_experience", "option_id": "1_to_3_years"},
        {"question_id": "product_knowledge", "option_id": "basic"},
        {"question_id": "investment_horizon", "option_id": "3_to_5_years"},
        {"question_id": "investment_goal", "option_id": "retirement"},
        {"question_id": "loss_tolerance", "option_id": "loss_20_percent"},
        {"question_id": "risk_return_preference", "option_id": "balanced"},
        {"question_id": "investable_asset_ratio", "option_id": "10_to_30_percent"},
        {"question_id": "annual_income", "option_id": "30m_to_50m"},
    ],
}


class FakeService:
    def __init__(self, error: ServiceError | None = None) -> None:
        self.error = error
        self.requests = []

    async def analyze(self, user_id, request):
        self.requests.append((user_id, request))
        if self.error:
            raise self.error
        return InvestorProfileResponse(
            assessment_id=uuid4(),
            questionnaire_version="v1",
            profile_type="중립투자형",
            tendency_line="안정성과 수익의 균형을 중요하게 생각하는 투자자예요.",
            description="일정 수준의 변동은 감수하지만 과도한 위험은 피하는 성향입니다.",
            traits={"stability": 3, "return_seeking": 3, "horizon": 4},
            analysis_summary=["20% 수준의 손실을 감당할 수 있다고 응답했습니다."],
            model_version="profile-model-v1",
            created_at=datetime(2026, 8, 24, tzinfo=UTC),
        )

    def latest(self, user_id):
        self.requests.append((user_id, "latest"))
        return InvestorProfileResponse(
            assessment_id=uuid4(),
            questionnaire_version="v1",
            profile_type="중립투자형",
            tendency_line="안정성과 수익의 균형을 중요하게 생각하는 투자자예요.",
            description="일정 수준의 변동은 감수하지만 과도한 위험은 피하는 성향입니다.",
            traits={"stability": 3, "return_seeking": 3, "horizon": 4},
            analysis_summary=["20% 수준의 손실을 감당할 수 있다고 응답했습니다."],
            model_version="profile-model-v1",
            created_at=datetime(2026, 8, 24, tzinfo=UTC),
        )


def install_overrides(service: FakeService) -> None:
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_investor_profile_service] = lambda: service


def test_analyze_api_returns_model_result_in_same_request() -> None:
    service = FakeService()
    install_overrides(service)
    try:
        response = TestClient(app).post("/api/v1/investor-profile/analyze", json=PAYLOAD)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(service.requests) == 1
    assert service.requests[0][0] == 7
    body = response.json()
    UUID(body.pop("assessment_id"))
    assert body == {
        "profile_type": "중립투자형",
        "tendency_line": "안정성과 수익의 균형을 중요하게 생각하는 투자자예요.",
        "description": "일정 수준의 변동은 감수하지만 과도한 위험은 피하는 성향입니다.",
        "traits": {"stability": 3, "return_seeking": 3, "horizon": 4},
        "analysis_summary": ["20% 수준의 손실을 감당할 수 있다고 응답했습니다."],
        "questionnaire_version": "v1",
        "analysis_version": "v1",
        "model_version": "profile-model-v1",
        "created_at": "2026-08-24T00:00:00Z",
    }


def test_analyze_api_preserves_service_error_contract() -> None:
    service = FakeService(ServiceError("AI_ANALYSIS_TIMEOUT", "분석 시간 초과", 504))
    install_overrides(service)
    try:
        response = TestClient(app).post("/api/v1/investor-profile/analyze", json=PAYLOAD)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 504
    assert response.json() == {"code": "AI_ANALYSIS_TIMEOUT", "message": "분석 시간 초과"}


def test_analyze_api_requires_authentication() -> None:
    response = TestClient(app).post("/api/v1/investor-profile/analyze", json=PAYLOAD)
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_latest_profile_uses_authenticated_user() -> None:
    service = FakeService()
    install_overrides(service)
    try:
        response = TestClient(app).get("/api/v1/investor-profile/me/latest")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert service.requests == [(7, "latest")]
