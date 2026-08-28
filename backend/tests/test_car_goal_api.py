"""목표 차량 API가 current_amount를 요청으로 받지 않고 인증을 요구하는지 검증한다."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes.car_goal import get_car_goal_service
from app.main import app


NOW = datetime(2026, 8, 28, tzinfo=UTC)


class FakeCarGoalService:
    def __init__(self) -> None:
        self.calls = []

    def get(self, user):
        self.calls.append(("get", user.id))
        return SimpleNamespace(
            car_grade="INEX",
            goal_amount=Decimal("10000000"),
            current_amount=Decimal("3000000"),
            updated_at=NOW,
        )

    def upsert(self, user, car_grade, goal_amount):
        self.calls.append(("upsert", user.id, car_grade, goal_amount))
        # 서버가 실제 계좌를 조회해 계산했다고 가정한 값 — 요청 본문에는 없던 값이다.
        return SimpleNamespace(
            car_grade=car_grade,
            goal_amount=goal_amount,
            current_amount=Decimal("5000000"),
            updated_at=NOW,
        )


def install(service: FakeCarGoalService) -> None:
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7, active_operation_mode="SEMI_AUTO")
    app.dependency_overrides[get_car_goal_service] = lambda: service


def test_upsert_rejects_client_supplied_current_amount() -> None:
    """current_amount는 조작 가능한 클라이언트 입력이라 스키마 자체가 거부해야 한다."""

    service = FakeCarGoalService()
    install(service)
    try:
        response = TestClient(app).put(
            "/api/v1/me/car-goal",
            json={"car_grade": "HIGHEND", "goal_amount": 50_000_000, "current_amount": 999_999_999},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert service.calls == []


def test_upsert_passes_only_grade_and_goal_amount_to_service() -> None:
    service = FakeCarGoalService()
    install(service)
    try:
        response = TestClient(app).put(
            "/api/v1/me/car-goal",
            json={"car_grade": "HIGHEND", "goal_amount": 50_000_000},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    # 응답의 current_amount는 요청에 없던, 서비스(=서버)가 계산해 돌려준 값이다.
    assert body["current_amount"] == "5000000"
    assert service.calls == [("upsert", 7, "HIGHEND", Decimal("50000000"))]


def test_get_requires_authentication() -> None:
    response = TestClient(app).get("/api/v1/me/car-goal")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_upsert_requires_authentication() -> None:
    response = TestClient(app).put(
        "/api/v1/me/car-goal",
        json={"car_grade": "INEX", "goal_amount": 10_000_000},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
