"""ACS Email 발송과 Redis 상태를 조합한 이메일 소유 검증 서비스."""

from dataclasses import dataclass
from hashlib import sha256
import hmac
import secrets
from uuid import UUID, uuid4

import redis

from app.core.config import Settings, settings
from app.core.errors import ServiceError
from app.integrations.acs.email import AcsEmailSender, VerificationEmailSender
from app.repositories.email_verification import (
    ChallengeResult,
    RedisEmailVerificationRepository,
    SendSlotResult,
    TokenReservationResult,
)


@dataclass(frozen=True)
class EmailChallenge:
    verification_id: UUID
    expires_in_seconds: int
    resend_after_seconds: int


@dataclass(frozen=True)
class EmailVerificationProof:
    verification_token: str
    expires_in_seconds: int


@dataclass(frozen=True)
class EmailTokenReservation:
    token_hash: str
    reservation_id: UUID


class EmailVerificationService:
    """이메일 OTP를 발급하고 가입 시 한 번만 사용할 수 있는 증명으로 교환한다."""

    def __init__(
        self,
        repository: RedisEmailVerificationRepository | None = None,
        sender: VerificationEmailSender | None = None,
        configuration: Settings = settings,
    ) -> None:
        self.configuration = configuration
        self.repository = repository or RedisEmailVerificationRepository(
            redis.from_url(
                configuration.redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
            )
        )
        self.sender = sender or AcsEmailSender(
            configuration.acs_email_connection_string,
            configuration.acs_email_sender_address,
        )

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    def send_code(self, email: str, client_address: str | None = None) -> EmailChallenge:
        self._ensure_configured()
        normalized = self.normalize_email(email)
        target_hash = sha256(normalized.encode()).hexdigest()
        client_hash = sha256((client_address or "unknown").encode()).hexdigest()
        try:
            slot = self.repository.acquire_send_slot(
                target_hash,
                client_hash,
                self.configuration.email_otp_resend_seconds,
                self.configuration.email_otp_hourly_limit,
                self.configuration.email_otp_ip_hourly_limit,
            )
        except redis.RedisError as exc:
            raise self._redis_unavailable() from exc
        if slot == SendSlotResult.COOLDOWN:
            raise ServiceError(
                "EMAIL_VERIFICATION_COOLDOWN",
                "인증번호를 다시 받기 전에 잠시 기다려 주세요.",
                429,
            )
        if slot in (SendSlotResult.HOURLY_LIMIT, SendSlotResult.IP_HOURLY_LIMIT):
            raise ServiceError(
                "EMAIL_VERIFICATION_RATE_LIMITED",
                "인증번호 요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.",
                429,
            )

        verification_id = uuid4()
        code = f"{secrets.randbelow(1_000_000):06d}"
        digest = self._code_digest(verification_id, code)
        try:
            self.repository.create_challenge(
                verification_id,
                target_hash,
                normalized,
                digest,
                self.configuration.email_otp_ttl_seconds,
                self.configuration.email_otp_max_attempts,
            )
        except redis.RedisError as exc:
            raise self._redis_unavailable() from exc

        try:
            self.sender.send_verification_code(
                normalized,
                code,
                max(1, self.configuration.email_otp_ttl_seconds // 60),
            )
        except Exception as exc:
            try:
                self.repository.discard_challenge(verification_id, target_hash)
                self.repository.release_cooldown(target_hash)
            except redis.RedisError:
                pass
            if isinstance(exc, ServiceError):
                raise
            raise ServiceError(
                "EMAIL_DELIVERY_FAILED",
                "인증 이메일을 발송하지 못했습니다. 잠시 후 다시 시도해 주세요.",
                502,
            ) from exc
        return EmailChallenge(
            verification_id,
            self.configuration.email_otp_ttl_seconds,
            self.configuration.email_otp_resend_seconds,
        )

    def verify_code(self, verification_id: UUID, code: str) -> EmailVerificationProof:
        self._ensure_configured()
        digest = self._code_digest(verification_id, code)
        try:
            result = self.repository.verify_challenge(
                verification_id,
                digest,
                self.configuration.email_otp_max_attempts,
            )
        except redis.RedisError as exc:
            raise self._redis_unavailable() from exc
        if result.result == ChallengeResult.EXPIRED:
            raise ServiceError(
                "EMAIL_VERIFICATION_EXPIRED",
                "인증번호가 만료됐거나 존재하지 않습니다.",
            )
        if result.result == ChallengeResult.LOCKED:
            raise ServiceError(
                "EMAIL_VERIFICATION_ATTEMPTS_EXCEEDED",
                "인증번호 입력 횟수를 초과했습니다. 새 인증번호를 요청해 주세요.",
                429,
            )
        if result.result == ChallengeResult.INVALID:
            raise ServiceError(
                "EMAIL_VERIFICATION_CODE_INVALID",
                "인증번호가 올바르지 않습니다.",
            )

        token = secrets.token_urlsafe(32)
        token_hash = self._token_hash(token)
        try:
            self.repository.create_verification_token(
                token_hash,
                result.email or "",
                self.configuration.email_verification_token_ttl_seconds,
            )
        except redis.RedisError as exc:
            raise self._redis_unavailable() from exc
        return EmailVerificationProof(
            token,
            self.configuration.email_verification_token_ttl_seconds,
        )

    def reserve_token(self, token: str, email: str) -> EmailTokenReservation:
        normalized = self.normalize_email(email)
        token_hash = self._token_hash(token)
        reservation_id = uuid4()
        try:
            result = self.repository.reserve_token(token_hash, normalized, reservation_id)
        except redis.RedisError as exc:
            raise self._redis_unavailable() from exc
        if result != TokenReservationResult.RESERVED:
            raise ServiceError(
                "EMAIL_VERIFICATION_REQUIRED",
                "이메일 인증이 만료됐거나 가입 정보와 일치하지 않습니다.",
            )
        return EmailTokenReservation(token_hash, reservation_id)

    def release_token(self, reservation: EmailTokenReservation) -> None:
        self.repository.release_token(reservation.token_hash, reservation.reservation_id)

    def finalize_token(self, reservation: EmailTokenReservation) -> None:
        self.repository.finalize_token(reservation.token_hash, reservation.reservation_id)

    def _code_digest(self, verification_id: UUID, code: str) -> str:
        payload = f"{verification_id}:{code}".encode()
        return hmac.new(
            self.configuration.email_otp_secret.encode(),
            payload,
            sha256,
        ).hexdigest()

    @staticmethod
    def _token_hash(token: str) -> str:
        return sha256(token.encode()).hexdigest()

    def _ensure_configured(self) -> None:
        if not self.configuration.email_verification_configured:
            raise ServiceError(
                "EMAIL_VERIFICATION_UNAVAILABLE",
                "이메일 인증 서비스가 설정되지 않았습니다.",
                503,
            )

    @staticmethod
    def _redis_unavailable() -> ServiceError:
        return ServiceError(
            "EMAIL_VERIFICATION_UNAVAILABLE",
            "이메일 인증 상태 저장소를 사용할 수 없습니다.",
            503,
        )
