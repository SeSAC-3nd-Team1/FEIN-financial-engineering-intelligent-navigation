"""Redis 기반 이메일 OTP와 1회성 가입 증명 저장소."""

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

import redis


class SendSlotResult(Enum):
    ACQUIRED = "ACQUIRED"
    COOLDOWN = "COOLDOWN"
    HOURLY_LIMIT = "HOURLY_LIMIT"
    IP_HOURLY_LIMIT = "IP_HOURLY_LIMIT"


class ChallengeResult(Enum):
    VERIFIED = "VERIFIED"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"
    LOCKED = "LOCKED"


class TokenReservationResult(Enum):
    RESERVED = "RESERVED"
    INVALID = "INVALID"
    EMAIL_MISMATCH = "EMAIL_MISMATCH"
    ALREADY_USED = "ALREADY_USED"


@dataclass(frozen=True)
class ChallengeVerification:
    result: ChallengeResult
    email: str | None = None


class RedisEmailVerificationRepository:
    """원자적 Lua 연산으로 OTP 시도와 가입 토큰의 단일 사용을 보장한다."""

    _SEND_SLOT_SCRIPT = """
    if redis.call('EXISTS', KEYS[1]) == 1 then return -1 end
    local target_count = tonumber(redis.call('GET', KEYS[2]) or '0')
    if target_count >= tonumber(ARGV[3]) then return -2 end
    local ip_count = tonumber(redis.call('GET', KEYS[3]) or '0')
    if ip_count >= tonumber(ARGV[4]) then return -3 end
    redis.call('SET', KEYS[1], '1', 'EX', ARGV[1])
    target_count = redis.call('INCR', KEYS[2])
    if target_count == 1 then redis.call('EXPIRE', KEYS[2], ARGV[2]) end
    ip_count = redis.call('INCR', KEYS[3])
    if ip_count == 1 then redis.call('EXPIRE', KEYS[3], ARGV[2]) end
    return target_count
    """

    _DISCARD_SCRIPT = """
    redis.call('DEL', KEYS[1])
    if redis.call('GET', KEYS[2]) == ARGV[1] then redis.call('DEL', KEYS[2]) end
    return 1
    """

    _VERIFY_SCRIPT = """
    if redis.call('EXISTS', KEYS[1]) == 0 then return {-1, ''} end
    local attempts = tonumber(redis.call('HGET', KEYS[1], 'attempts') or '0')
    local max_attempts = tonumber(redis.call('HGET', KEYS[1], 'max_attempts') or ARGV[2])
    if attempts >= max_attempts then
        redis.call('DEL', KEYS[1])
        return {-2, ''}
    end
    if redis.call('HGET', KEYS[1], 'code_digest') ~= ARGV[1] then
        attempts = redis.call('HINCRBY', KEYS[1], 'attempts', 1)
        if attempts >= max_attempts then
            redis.call('DEL', KEYS[1])
            return {-2, ''}
        end
        return {0, ''}
    end
    local email = redis.call('HGET', KEYS[1], 'email')
    redis.call('DEL', KEYS[1])
    return {1, email}
    """

    _RESERVE_TOKEN_SCRIPT = """
    if redis.call('EXISTS', KEYS[1]) == 0 then return 0 end
    if redis.call('HGET', KEYS[1], 'email') ~= ARGV[1] then return -1 end
    if redis.call('HGET', KEYS[1], 'state') ~= 'ISSUED' then return -2 end
    redis.call('HSET', KEYS[1], 'state', 'RESERVED', 'reservation_id', ARGV[2])
    return 1
    """

    _RELEASE_TOKEN_SCRIPT = """
    if redis.call('HGET', KEYS[1], 'state') == 'RESERVED'
       and redis.call('HGET', KEYS[1], 'reservation_id') == ARGV[1] then
        redis.call('HSET', KEYS[1], 'state', 'ISSUED')
        redis.call('HDEL', KEYS[1], 'reservation_id')
        return 1
    end
    return 0
    """

    _FINALIZE_TOKEN_SCRIPT = """
    if redis.call('HGET', KEYS[1], 'state') == 'RESERVED'
       and redis.call('HGET', KEYS[1], 'reservation_id') == ARGV[1] then
        return redis.call('DEL', KEYS[1])
    end
    return 0
    """

    def __init__(self, cache: redis.Redis) -> None:
        self.cache = cache

    @staticmethod
    def _challenge_key(verification_id: UUID | str) -> str:
        return f"auth:email-otp:{verification_id}"

    @staticmethod
    def _active_key(target_hash: str) -> str:
        return f"auth:email-otp-active:{target_hash}"

    @staticmethod
    def _token_key(token_hash: str) -> str:
        return f"auth:email-verification-token:{token_hash}"

    def acquire_send_slot(
        self,
        target_hash: str,
        client_hash: str,
        resend_seconds: int,
        hourly_limit: int,
        ip_hourly_limit: int,
    ) -> SendSlotResult:
        result = int(self.cache.eval(
            self._SEND_SLOT_SCRIPT,
            3,
            f"auth:email-send-cooldown:{target_hash}",
            f"auth:email-send-hourly:{target_hash}",
            f"auth:email-send-ip-hourly:{client_hash}",
            resend_seconds,
            3600,
            hourly_limit,
            ip_hourly_limit,
        ))
        if result == -1:
            return SendSlotResult.COOLDOWN
        if result == -2:
            return SendSlotResult.HOURLY_LIMIT
        if result == -3:
            return SendSlotResult.IP_HOURLY_LIMIT
        return SendSlotResult.ACQUIRED

    def release_cooldown(self, target_hash: str) -> None:
        self.cache.delete(f"auth:email-send-cooldown:{target_hash}")

    def create_challenge(
        self,
        verification_id: UUID,
        target_hash: str,
        email: str,
        code_digest: str,
        ttl_seconds: int,
        max_attempts: int,
    ) -> None:
        active_key = self._active_key(target_hash)
        previous_id = self.cache.get(active_key)
        with self.cache.pipeline(transaction=True) as pipeline:
            if previous_id:
                pipeline.delete(self._challenge_key(previous_id))
            challenge_key = self._challenge_key(verification_id)
            pipeline.hset(challenge_key, mapping={
                "email": email,
                "code_digest": code_digest,
                "attempts": 0,
                "max_attempts": max_attempts,
            })
            pipeline.expire(challenge_key, ttl_seconds)
            pipeline.set(active_key, str(verification_id), ex=ttl_seconds)
            pipeline.execute()

    def discard_challenge(self, verification_id: UUID, target_hash: str) -> None:
        self.cache.eval(
            self._DISCARD_SCRIPT,
            2,
            self._challenge_key(verification_id),
            self._active_key(target_hash),
            str(verification_id),
        )

    def verify_challenge(
        self,
        verification_id: UUID,
        code_digest: str,
        max_attempts: int,
    ) -> ChallengeVerification:
        result = self.cache.eval(
            self._VERIFY_SCRIPT,
            1,
            self._challenge_key(verification_id),
            code_digest,
            max_attempts,
        )
        status = int(result[0])
        if status == 1:
            return ChallengeVerification(ChallengeResult.VERIFIED, str(result[1]))
        if status == 0:
            return ChallengeVerification(ChallengeResult.INVALID)
        if status == -2:
            return ChallengeVerification(ChallengeResult.LOCKED)
        return ChallengeVerification(ChallengeResult.EXPIRED)

    def create_verification_token(self, token_hash: str, email: str, ttl_seconds: int) -> None:
        key = self._token_key(token_hash)
        with self.cache.pipeline(transaction=True) as pipeline:
            pipeline.hset(key, mapping={"email": email, "state": "ISSUED"})
            pipeline.expire(key, ttl_seconds)
            pipeline.execute()

    def reserve_token(
        self,
        token_hash: str,
        email: str,
        reservation_id: UUID,
    ) -> TokenReservationResult:
        result = int(self.cache.eval(
            self._RESERVE_TOKEN_SCRIPT,
            1,
            self._token_key(token_hash),
            email,
            str(reservation_id),
        ))
        if result == 1:
            return TokenReservationResult.RESERVED
        if result == -1:
            return TokenReservationResult.EMAIL_MISMATCH
        if result == -2:
            return TokenReservationResult.ALREADY_USED
        return TokenReservationResult.INVALID

    def release_token(self, token_hash: str, reservation_id: UUID) -> None:
        self.cache.eval(
            self._RELEASE_TOKEN_SCRIPT,
            1,
            self._token_key(token_hash),
            str(reservation_id),
        )

    def finalize_token(self, token_hash: str, reservation_id: UUID) -> None:
        self.cache.eval(
            self._FINALIZE_TOKEN_SCRIPT,
            1,
            self._token_key(token_hash),
            str(reservation_id),
        )
