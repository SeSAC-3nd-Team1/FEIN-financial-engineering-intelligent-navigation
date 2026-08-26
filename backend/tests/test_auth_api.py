"""인증 사용자 조회에서 활성 운용방식 복원 정보를 검증한다."""

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.main import app


def test_me_returns_active_operation_mode() -> None:
    changed_at = datetime(2026, 8, 25, tzinfo=UTC)
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(
        id=7,
        user_id="testuser",
        name="테스트",
        email="test@example.com",
        account_status="ACTIVE",
        active_operation_mode="AUTO",
        operation_mode_changed_at=changed_at,
    )
    try:
        response = TestClient(app).get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["active_operation_mode"] == "AUTO"
    assert datetime.fromisoformat(
        response.json()["operation_mode_changed_at"].replace("Z", "+00:00")
    ) == changed_at
