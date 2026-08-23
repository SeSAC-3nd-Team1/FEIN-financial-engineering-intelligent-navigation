"""KIS Open API의 토큰과 국내주식 현재가만 담당한다.

주문 endpoint는 의도적으로 제공하지 않는다. 실제 주문/잔액은 서비스 DB의 가상 거래 엔진이 관리한다.
"""

from datetime import UTC, datetime
from decimal import Decimal
import logging
import time

import httpx
import redis

from app.core.config import settings
from app.core.errors import ServiceError

logger = logging.getLogger(__name__)


class KisClient:
    TOKEN_CACHE_KEY = "kis:oauth:access_token"

    def __init__(self, cache: redis.Redis | None = None) -> None:
        self.cache = cache
        self._token: str | None = None
        self._token_expires_at = 0.0

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        if self.cache is not None:
            try:
                cached = self.cache.get(self.TOKEN_CACHE_KEY)
                if cached:
                    if isinstance(cached, bytes):
                        cached = cached.decode()
                    self._token = cached
                    return cached
            except redis.RedisError:
                logger.warning("Redis KIS token cache unavailable")
        if not settings.kis_app_key or not settings.kis_app_secret:
            raise ServiceError("KIS_NOT_CONFIGURED", "KIS API credential이 설정되지 않았습니다.", 503)
        try:
            response = httpx.post(
                f"{settings.kis_base_url}/oauth2/tokenP",
                json={"grant_type": "client_credentials", "appkey": settings.kis_app_key, "appsecret": settings.kis_app_secret},
                timeout=settings.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("KIS token request failed: %s", type(exc).__name__)
            raise ServiceError("KIS_UNAVAILABLE", "현재 시장가격 제공자를 사용할 수 없습니다.", 503) from exc
        self._token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self._token_expires_at = time.time() + expires_in
        if self.cache is not None:
            try:
                self.cache.setex(self.TOKEN_CACHE_KEY, max(1, expires_in - 60), self._token)
            except redis.RedisError:
                logger.warning("Redis KIS token cache write failed")
        return self._token

    def get_current_price(self, stock_code: str) -> tuple[Decimal, datetime]:
        headers = {
            "authorization": f"Bearer {self._access_token()}",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
            "tr_id": "FHKST01010100",
            "custtype": "P",
        }
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = httpx.get(
                    f"{settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-price",
                    headers=headers,
                    params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code},
                    timeout=settings.request_timeout_seconds,
                )
                if response.status_code == 429:
                    raise ServiceError("KIS_RATE_LIMIT", "시장가격 조회 한도를 초과했습니다.", 503)
                response.raise_for_status()
                payload = response.json()
                if payload.get("rt_cd") != "0":
                    raise ServiceError("STOCK_NOT_FOUND", "조회할 수 없는 종목입니다.", 404)
                return Decimal(payload["output"]["stck_prpr"]), datetime.now(UTC)
            except ServiceError:
                raise
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                last_error = exc
                logger.warning("KIS price request attempt=%s failed stock_code=%s error=%s", attempt + 1, stock_code, type(exc).__name__)
        raise ServiceError("KIS_UNAVAILABLE", "현재 시장가격을 조회하지 못했습니다.", 503) from last_error
