"""Redis 우선 현재가 조회와 KIS fallback."""

from datetime import UTC, datetime
from decimal import Decimal
import json
import logging

import redis

from app.core.config import settings
from app.integrations.kis.client import KisClient
from app.integrations.kis.hub import REALTIME_PRICE_KEY_PREFIX
from app.integrations.kis.models import RealtimeQuote

logger = logging.getLogger(__name__)


class MarketService:
    def __init__(self, kis: KisClient | None = None, cache: redis.Redis | None = None) -> None:
        self.cache = cache or redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1)
        self.kis = kis or KisClient(cache=self.cache)

    def get_price(self, stock_code: str) -> tuple[Decimal, datetime, str]:
        realtime_key = f"{REALTIME_PRICE_KEY_PREFIX}{stock_code}"
        try:
            realtime_cached = self.cache.get(realtime_key)
            if realtime_cached:
                quote = RealtimeQuote.from_cache_json(realtime_cached)
                age = (datetime.now(UTC) - quote.received_at.astimezone(UTC)).total_seconds()
                if age <= settings.realtime_price_stale_seconds:
                    return quote.price, quote.traded_at, "KIS_WS"
                logger.info("Ignoring stale realtime price stock_code=%s age_seconds=%.3f", stock_code, age)
        except (redis.RedisError, ValueError, TypeError):
            logger.warning("Redis realtime price unavailable stock_code=%s", stock_code)

        key = f"price:{stock_code}"
        try:
            cached = self.cache.get(key)
            if cached:
                payload = json.loads(cached)
                return Decimal(payload["price"]), datetime.fromisoformat(payload["as_of"]), "REDIS"
        except (redis.RedisError, ValueError, KeyError):
            logger.warning("Redis price cache unavailable stock_code=%s", stock_code)

        price, as_of = self.kis.get_current_price(stock_code)
        try:
            self.cache.setex(key, settings.price_cache_ttl_seconds, json.dumps({"price": str(price), "as_of": as_of.isoformat()}))
        except redis.RedisError:
            logger.warning("Redis price cache write failed stock_code=%s", stock_code)
        return price, as_of, "KIS"
