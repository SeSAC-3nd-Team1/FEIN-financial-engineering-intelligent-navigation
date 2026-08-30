from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import ServiceError
from app.schemas.api import SignupRequest
from app.services.auth import AuthService
from app.services.email_verification import EmailTokenReservation


class EmptyCatalogSession:
    def scalars(self, _statement):
        return []


def test_terms_catalog_fails_closed_without_required_terms() -> None:
    with pytest.raises(ServiceError) as error:
        AuthService(EmptyCatalogSession()).signup_terms()

    assert error.value.code == "TERMS_CATALOG_UNAVAILABLE"
    assert error.value.status_code == 503


def test_signup_request_rejects_client_declared_verification_flags() -> None:
    with pytest.raises(ValidationError) as error:
        SignupRequest(
            user_id="tester01",
            password="Password!1",
            name="테스트",
            birthdate="900101",
            phone_number="01012345678",
            email="user@example.com",
            email_verification_token="x" * 32,
            phone_verified=True,
            email_verified=True,
            agreements=[],
        )

    assert {item["loc"] for item in error.value.errors()} == {
        ("phone_verified",),
        ("email_verified",),
    }


def test_signup_request_requires_server_issued_email_verification_token() -> None:
    with pytest.raises(ValidationError) as error:
        SignupRequest(
            user_id="tester01",
            password="Password!1",
            name="테스트",
            birthdate="900101",
            phone_number="01012345678",
            email="user@example.com",
            agreements=[],
        )

    assert ("email_verification_token",) in {
        item["loc"] for item in error.value.errors()
    }


class SignupSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0
        self.term = SimpleNamespace(
            id=11,
            term_code="B_PRIVACY",
            version="v1",
            is_required=True,
            effective_at=datetime.now(UTC),
        )

    def scalar(self, _statement):
        return None

    def scalars(self, _statement):
        return [self.term]

    def add(self, value) -> None:
        self.added.append(value)

    def flush(self) -> None:
        self.added[0].id = 7

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None

    def refresh(self, _value) -> None:
        raise AssertionError("signup must not refresh after a successful commit")


class SignupVerifier:
    def __init__(self) -> None:
        self.reserved_email = None
        self.finalized = False
        self.released = False

    def reserve_token(self, _token: str, email: str) -> EmailTokenReservation:
        self.reserved_email = email
        return EmailTokenReservation("token-hash", uuid4())

    def finalize_token(self, _reservation: EmailTokenReservation) -> None:
        self.finalized = True

    def release_token(self, _reservation: EmailTokenReservation) -> None:
        self.released = True


class FailingSignupSession(SignupSession):
    def flush(self) -> None:
        raise RuntimeError("database failure")


def test_signup_uses_server_email_proof() -> None:
    session = SignupSession()
    verifier = SignupVerifier()
    request = SignupRequest(
        user_id="tester01",
        password="Password!1",
        name="테스트",
        birthdate="900101",
        phone_number="01012345678",
        email="USER@example.com",
        email_verification_token="x" * 32,
        agreements=[{"term_code": "B_PRIVACY", "version": "v1", "agreed": True}],
    )

    user = AuthService(session, verifier).signup(request)

    assert verifier.reserved_email == "user@example.com"
    assert verifier.finalized
    assert session.commits == 1
    assert user.email_verified_at is not None


def _birthdate_for_age(age: int) -> str:
    """오늘 기준 만 `age`세가 되는 YYMMDD를 만든다 — 하드코딩된 연도로 인한 시간 경과 시 테스트
    깨짐을 방지한다."""
    today = datetime.now(UTC).date()
    year = today.year - age
    return f"{year % 100:02d}{today.month:02d}{today.day:02d}"


def test_signup_rejects_underage_applicant() -> None:
    session = SignupSession()
    verifier = SignupVerifier()
    request = SignupRequest(
        user_id="tester03",
        password="Password!1",
        name="테스트",
        birthdate=_birthdate_for_age(10),
        phone_number="01012345678",
        email="user@example.com",
        email_verification_token="x" * 32,
        agreements=[{"term_code": "B_PRIVACY", "version": "v1", "agreed": True}],
    )

    with pytest.raises(ServiceError) as error:
        AuthService(session, verifier).signup(request)

    assert error.value.code == "UNDERAGE"
    assert session.commits == 0


def test_signup_releases_reserved_email_proof_when_database_write_fails() -> None:
    session = FailingSignupSession()
    verifier = SignupVerifier()
    request = SignupRequest(
        user_id="tester02",
        password="Password!1",
        name="테스트",
        birthdate="900101",
        phone_number="01012345678",
        email="user@example.com",
        email_verification_token="x" * 32,
        agreements=[{"term_code": "B_PRIVACY", "version": "v1", "agreed": True}],
    )

    with pytest.raises(RuntimeError, match="database failure"):
        AuthService(session, verifier).signup(request)

    assert verifier.released
    assert not verifier.finalized
