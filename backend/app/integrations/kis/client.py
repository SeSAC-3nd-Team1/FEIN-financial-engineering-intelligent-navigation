"""KIS Open API의 토큰과 국내주식 현재가만 담당한다.

주문 endpoint는 의도적으로 제공하지 않는다. 실제 주문/잔액은 서비스 DB의 가상 거래 엔진이 관리한다.
"""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import logging
import time

import httpx
import redis

from app.core.config import settings
from app.core.errors import ServiceError
from app.integrations.kis.models import CurrentQuote, MinuteCandle

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
KIS_RATE_LIMIT_MESSAGE_CODE = "EGW00201"
KIS_RATE_LIMIT_ATTEMPTS = 3


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
            access_token = payload["access_token"]
            expires_in = int(payload.get("expires_in", 3600))
            if not isinstance(access_token, str) or not access_token or expires_in <= 0:
                raise ValueError("invalid token response")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning("KIS token request failed: %s", type(exc).__name__)
            raise ServiceError("KIS_UNAVAILABLE", "현재 시장가격 제공자를 사용할 수 없습니다.", 503) from exc
        self._token = access_token
        self._token_expires_at = time.time() + expires_in
        if self.cache is not None:
            try:
                self.cache.setex(self.TOKEN_CACHE_KEY, max(1, expires_in - 60), self._token)
            except redis.RedisError:
                logger.warning("Redis KIS token cache write failed")
        return self._token

    def get_current_quote(self, stock_code: str) -> CurrentQuote:
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
                output = payload["output"]
                price = Decimal(output["stck_prpr"])
                if not price.is_finite() or price <= 0:
                    raise ValueError("invalid current price")
                change_amount = self._optional_decimal(output.get("prdy_vrss"))
                previous_close = self._optional_decimal(output.get("stck_sdpr"))
                if previous_close is None and change_amount is not None and price - change_amount > 0:
                    previous_close = price - change_amount
                return CurrentQuote(
                    stock_code=stock_code,
                    price=price,
                    previous_close=previous_close,
                    change_amount=change_amount,
                                        change_rate=self._optional_decimal(output.get("prdy_ctrt")),
                    volume=self._optional_int(output.get("acml_vol")),

                    as_of=datetime.now(UTC),
                    per=self._optional_decimal(output.get("per")),
                    pbr=self._optional_decimal(output.get("pbr")),
                    eps=self._optional_decimal(output.get("eps")),
                    bps=self._optional_decimal(output.get("bps")),
                    roe=self._optional_decimal(output.get("roe")),
                )

            except ServiceError:
                raise
            except (httpx.HTTPError, InvalidOperation, ValueError, KeyError, TypeError) as exc:
                last_error = exc
                logger.warning("KIS price request attempt=%s failed stock_code=%s error=%s", attempt + 1, stock_code, type(exc).__name__)
        raise ServiceError("KIS_UNAVAILABLE", "현재 시장가격을 조회하지 못했습니다.", 503) from last_error

    def get_current_price(self, stock_code: str) -> tuple[Decimal, datetime]:
        """주문/평가 기존 계약을 유지하는 현재가 호환 wrapper다."""

        quote = self.get_current_quote(stock_code)
        return quote.price, quote.as_of

    @staticmethod
    def _optional_decimal(value: object) -> Decimal | None:
        if value in (None, ""):
            return None
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("invalid quote number")
        return result

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value in (None, ""):
            return None
        result = int(value)
        if result < 0:
            raise ValueError("invalid quote volume")
        return result

    def get_minute_candles(
        self,
        stock_code: str,
        *,
        limit: int = 120,
        end_at: datetime | None = None,
    ) -> tuple[list[MinuteCandle], datetime]:
        """KIS 당일 분봉 API를 페이지당 최대 30건씩 조회한다."""
        if not 1 <= limit <= 390:
            raise ValueError("limit must be between 1 and 390")

        requested_at = (end_at or datetime.now(KST)).astimezone(KST)
        cursor = requested_at
        candles: dict[datetime, MinuteCandle] = {}
        headers = {
            "authorization": f"Bearer {self._access_token()}",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
            "tr_id": "FHKST03010200",
            "custtype": "P",
        }

        for page_index in range((limit + 29) // 30):
            if page_index:
                # 모의투자 API의 낮은 초당 호출 제한에서도 390분봉 pagination이 burst가 되지 않게 한다.
                time.sleep(max(0, settings.kis_rest_page_interval_seconds))
            rows = self._get_minute_candle_page(stock_code, cursor, headers)
            before_count = len(candles)
            parsed_count = 0
            for row in rows:
                try:
                    candle = self._parse_minute_candle(stock_code, row, requested_at)
                    candles[candle.started_at] = candle
                    parsed_count += 1
                except ValueError:
                    logger.warning("Ignoring invalid KIS minute candle row stock_code=%s", stock_code)

            if rows and parsed_count == 0:
                raise ServiceError("KIS_UNAVAILABLE", "분봉 데이터 형식이 올바르지 않습니다.", 503)

            if len(candles) >= limit or len(candles) == before_count:
                break
            earliest = min(candles)
            next_cursor = earliest - timedelta(minutes=1)
            if next_cursor.date() != requested_at.date():
                break
            cursor = next_cursor

        ordered = sorted(candles.values(), key=lambda candle: candle.started_at)
        return ordered[-limit:], datetime.now(UTC)

    def _get_minute_candle_page(
        self,
        stock_code: str,
        cursor: datetime,
        headers: dict[str, str],
    ) -> list[dict[str, object]]:
        last_error: Exception | None = None
        for attempt in range(KIS_RATE_LIMIT_ATTEMPTS):
            try:
                response = httpx.get(
                    f"{settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                    headers=headers,
                    params={
                        "FID_COND_MRKT_DIV_CODE": "J",
                        "FID_INPUT_ISCD": stock_code,
                        "FID_INPUT_HOUR_1": cursor.strftime("%H%M%S"),
                        "FID_PW_DATA_INCU_YN": "Y",
                        "FID_ETC_CLS_CODE": "",
                    },
                    timeout=settings.request_timeout_seconds,
                )
                if response.status_code == 429:
                    if attempt + 1 == KIS_RATE_LIMIT_ATTEMPTS:
                        raise ServiceError("KIS_RATE_LIMIT", "시장가격 조회 한도를 초과했습니다.", 503)
                    self._wait_for_rate_limit(attempt, stock_code)
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("invalid minute candle response")
                if payload.get("msg_cd") == KIS_RATE_LIMIT_MESSAGE_CODE:
                    if attempt + 1 == KIS_RATE_LIMIT_ATTEMPTS:
                        raise ServiceError("KIS_RATE_LIMIT", "시장가격 조회 한도를 초과했습니다.", 503)
                    self._wait_for_rate_limit(attempt, stock_code)
                    continue
                if payload.get("rt_cd") != "0":
                    raise ServiceError("STOCK_NOT_FOUND", "조회할 수 없는 종목입니다.", 404)
                rows = payload.get("output2")
                if not isinstance(rows, list):
                    raise ValueError("invalid minute candle response")
                return rows
            except ServiceError:
                raise
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                last_error = exc
                logger.warning(
                    "KIS minute candle request attempt=%s failed stock_code=%s error=%s",
                    attempt + 1,
                    stock_code,
                    type(exc).__name__,
                )
        raise ServiceError("KIS_UNAVAILABLE", "분봉 데이터를 조회하지 못했습니다.", 503) from last_error

    @staticmethod
    def _wait_for_rate_limit(attempt: int, stock_code: str) -> None:
        """KIS의 HTTP/업무 응답 rate limit을 동일한 지수 backoff로 재시도한다."""

        delay = max(0, settings.kis_rest_page_interval_seconds) * (2 ** attempt)
        logger.warning(
            "KIS minute candle rate limited stock_code=%s retry_after_seconds=%.3f",
            stock_code,
            delay,
        )
        if delay:
            time.sleep(delay)

    @staticmethod
    def _parse_minute_candle(
        stock_code: str,
        row: dict[str, object],
        requested_at: datetime,
    ) -> MinuteCandle:
        if not isinstance(row, dict):
            raise ValueError("invalid KIS minute candle row")
        try:
            business_date = str(row.get("stck_bsop_date") or requested_at.strftime("%Y%m%d"))
            trade_time = str(row["stck_cntg_hour"])
            started_at = datetime.strptime(f"{business_date}{trade_time}", "%Y%m%d%H%M%S").replace(
                second=0,
                microsecond=0,
                tzinfo=KST,
            )
            current_minute = requested_at.replace(second=0, microsecond=0)
            return MinuteCandle(
                stock_code=stock_code,
                started_at=started_at,
                open=Decimal(str(row["stck_oprc"])),
                high=Decimal(str(row["stck_hgpr"])),
                low=Decimal(str(row["stck_lwpr"])),
                close=Decimal(str(row["stck_prpr"])),
                volume=int(row["cntg_vol"]),
                is_closed=started_at < current_minute,
            )
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ValueError("invalid KIS minute candle row") from exc
