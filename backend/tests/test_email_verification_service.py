"""ACS Email과 Redis를 조합한 이메일 인증 서비스의 경계 동작을 검증한다."""

from dataclasses import replace
from hashlib import sha256
from uuid import UUID

import pytest

from app.core.config import settings
from app.core.errors import ServiceError
from app.repositories.email_verification import (
    ChallengeResult,
    ChallengeVerification,
    SendSlotResult,
    TokenReservationResult,
)
from app.services.email_verification import EmailVerificationService


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, int]] = []

    def send_verification_code(self, recipient: str, code: str, expires_minutes: int) -> None:
        self.messages.append((recipient, code, expires_minutes))


class FailingSender:
    def send_verification_code(self, _recipient: str, _code: str, _expires_minutes: int) -> None:
        raise RuntimeError("provider unavailable")


class FakeRepository:
    def __init__(self) -> None:
        self.slot_result = SendSlotResult.ACQUIRED
        self.send_slot_args = None
        self.challenges: dict[UUID, tuple[str, str]] = {}
        self.tokens: dict[str, dict[str, str]] = {}
        self.cooldown_released = False

    def acquire_send_slot(self, *args) -> SendSlotResult:
        self.send_slot_args = args
        return self.slot_result

    def release_cooldown(self, _target_hash: str) -> None:
        self.cooldown_released = True

    def create_challenge(
        self,
        verification_id: UUID,
        _target_hash: str,
        email: str,
        code_digest: str,
        _ttl_seconds: int,
        _max_attempts: int,
    ) -> None:
        self.challenges[verification_id] = (email, code_digest)

    def discard_challenge(self, verification_id: UUID, _target_hash: str) -> None:
        self.challenges.pop(verification_id, None)

    def verify_challenge(
        self,
        verification_id: UUID,
        code_digest: str,
        _max_attempts: int,
    ) -> ChallengeVerification:
        challenge = self.challenges.get(verification_id)
        if challenge is None:
            return ChallengeVerification(ChallengeResult.EXPIRED)
        email, expected_digest = challenge
        if code_digest != expected_digest:
            return ChallengeVerification(ChallengeResult.INVALID)
        del self.challenges[verification_id]
        return ChallengeVerification(ChallengeResult.VERIFIED, email)

    def create_verification_token(self, token_hash: str, email: str, _ttl_seconds: int) -> None:
        self.tokens[token_hash] = {"email": email, "state": "ISSUED"}

    def reserve_token(self, token_hash: str, email: str, reservation_id: UUID):
        token = self.tokens.get(token_hash)
        if token is None:
            return TokenReservationResult.INVALID
        if token["email"] != email:
            return TokenReservationResult.EMAIL_MISMATCH
        if token["state"] != "ISSUED":
            return TokenReservationResult.ALREADY_USED
        token.update(state="RESERVED", reservation_id=str(reservation_id))
        return TokenReservationResult.RESERVED

    def release_token(self, token_hash: str, reservation_id: UUID) -> None:
        token = self.tokens.get(token_hash)
        if token and token.get("reservation_id") == str(reservation_id):
            token.clear()
            token.update(email="test@example.com", state="ISSUED")

    def finalize_token(self, token_hash: str, reservation_id: UUID) -> None:
        token = self.tokens.get(token_hash)
        if token and token.get("reservation_id") == str(reservation_id):
            del self.tokens[token_hash]


def configured_service() -> tuple[EmailVerificationService, FakeRepository, FakeSender]:
    configuration = replace(
        settings,
        acs_email_connection_string="endpoint=https://example.invalid/;accessKey=test",
        acs_email_sender_address="DoNotReply@example.invalid",
        email_otp_secret="test-only-email-otp-secret",
    )
    repository = FakeRepository()
    sender = FakeSender()
    return EmailVerificationService(repository, sender, configuration), repository, sender


def test_send_verify_and_consume_token_once() -> None:
    service, repository, sender = configured_service()

    challenge = service.send_code("  User@Example.COM ", "203.0.113.10")
    assert sender.messages[0][0] == "user@example.com"
    assert sender.messages[0][1].isdigit()
    assert len(sender.messages[0][1]) == 6
    assert repository.send_slot_args == (
        sha256(b"user@example.com").hexdigest(),
        sha256(b"203.0.113.10").hexdigest(),
        service.configuration.email_otp_resend_seconds,
        service.configuration.email_otp_hourly_limit,
        service.configuration.email_otp_ip_hourly_limit,
    )

    proof = service.verify_code(challenge.verification_id, sender.messages[0][1])
    reservation = service.reserve_token(proof.verification_token, "USER@example.com")
    service.finalize_token(reservation)

    token_hash = sha256(proof.verification_token.encode()).hexdigest()
    assert token_hash not in repository.tokens
    with pytest.raises(ServiceError) as error:
        service.reserve_token(proof.verification_token, "user@example.com")
    assert error.value.code == "EMAIL_VERIFICATION_REQUIRED"


def test_verification_token_cannot_be_used_for_another_email() -> None:
    service, _repository, sender = configured_service()
    challenge = service.send_code("owner@example.com")
    proof = service.verify_code(challenge.verification_id, sender.messages[0][1])

    with pytest.raises(ServiceError) as error:
        service.reserve_token(proof.verification_token, "other@example.com")

    assert error.value.code == "EMAIL_VERIFICATION_REQUIRED"


@pytest.mark.parametrize(
    ("slot", "expected_code"),
    [
        (SendSlotResult.COOLDOWN, "EMAIL_VERIFICATION_COOLDOWN"),
        (SendSlotResult.HOURLY_LIMIT, "EMAIL_VERIFICATION_RATE_LIMITED"),
        (SendSlotResult.IP_HOURLY_LIMIT, "EMAIL_VERIFICATION_RATE_LIMITED"),
    ],
)
def test_send_rate_limits_are_reported(slot: SendSlotResult, expected_code: str) -> None:
    service, repository, _sender = configured_service()
    repository.slot_result = slot

    with pytest.raises(ServiceError) as error:
        service.send_code("test@example.com")

    assert error.value.code == expected_code
    assert error.value.status_code == 429


def test_invalid_code_does_not_issue_verification_token() -> None:
    service, repository, _sender = configured_service()
    challenge = service.send_code("test@example.com")

    with pytest.raises(ServiceError) as error:
        service.verify_code(challenge.verification_id, "000000")

    assert error.value.code == "EMAIL_VERIFICATION_CODE_INVALID"
    assert repository.tokens == {}


def test_missing_provider_configuration_fails_closed() -> None:
    configuration = replace(
        settings,
        acs_email_connection_string="",
        acs_email_sender_address="",
        email_otp_secret="",
    )
    service = EmailVerificationService(FakeRepository(), FakeSender(), configuration)

    with pytest.raises(ServiceError) as error:
        service.send_code("test@example.com")

    assert error.value.code == "EMAIL_VERIFICATION_UNAVAILABLE"
    assert error.value.status_code == 503


def test_provider_failure_discards_challenge_and_releases_cooldown() -> None:
    service, repository, _sender = configured_service()
    service.sender = FailingSender()

    with pytest.raises(ServiceError) as error:
        service.send_code("test@example.com")

    assert error.value.code == "EMAIL_DELIVERY_FAILED"
    assert error.value.status_code == 502
    assert repository.challenges == {}
    assert repository.cooldown_released
