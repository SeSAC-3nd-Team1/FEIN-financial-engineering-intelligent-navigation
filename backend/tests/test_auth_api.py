"""인증 사용자 조회에서 활성 운용방식 복원 정보를 검증한다."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes.auth import email_verification_service
from app.main import app
from app.services.email_verification import EmailChallenge, EmailVerificationProof


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


class VerificationStub:
    def __init__(self) -> None:
        self.verification_id = uuid4()

    def send_code(self, email: str, client_address: str | None = None) -> EmailChallenge:
        assert email == "test@example.com"
        assert client_address == "testclient"
        return EmailChallenge(self.verification_id, 300, 60)

    def verify_code(self, verification_id, code: str) -> EmailVerificationProof:
        assert verification_id == self.verification_id
        assert code == "123456"
        return EmailVerificationProof("v" * 43, 1800)


def test_email_verification_endpoints_return_server_proof() -> None:
    verification = VerificationStub()
    app.dependency_overrides[email_verification_service] = lambda: verification
    try:
        with TestClient(app) as client:
            sent = client.post(
                "/api/v1/auth/email-verifications/send",
                json={"email": "test@example.com"},
            )
            verified = client.post(
                "/api/v1/auth/email-verifications/verify",
                json={"verification_id": str(verification.verification_id), "code": "123456"},
            )
    finally:
        app.dependency_overrides.clear()

    assert sent.status_code == 202
    assert sent.json() == {
        "verification_id": str(verification.verification_id),
        "expires_in_seconds": 300,
        "resend_after_seconds": 60,
    }
    assert verified.status_code == 200
    assert verified.json() == {
        "verification_token": "v" * 43,
        "expires_in_seconds": 1800,
    }
