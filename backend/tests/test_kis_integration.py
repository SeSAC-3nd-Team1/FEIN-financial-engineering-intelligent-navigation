"""명시적으로 활성화할 때만 실제 KIS 시세→Redis 경로를 확인한다."""

import os

import pytest
import redis

from app.core.config import settings
from app.services.market import MarketService

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_KIS_INTEGRATION") != "1",
    reason="RUN_KIS_INTEGRATION=1 required",
)


def test_live_kis_quote_is_cached_without_placing_an_order() -> None:
    if not settings.kis_app_key or not settings.kis_app_secret:
        pytest.skip("KIS_APP_KEY and KIS_APP_SECRET are required")

    stock_code = os.getenv("KIS_TEST_STOCK_CODE", "005930")
    key = f"price:{stock_code}"
    cache = redis.from_url(settings.redis_url, decode_responses=True)
    cache.delete(key)
    try:
        price, _, source = MarketService(cache=cache).get_price(stock_code)
        assert price > 0
        assert source == "KIS"
        ttl = cache.ttl(key)
        assert 0 < ttl <= settings.price_cache_ttl_seconds

        cached_price, _, cached_source = MarketService(cache=cache).get_price(stock_code)
        assert cached_price == price
        assert cached_source == "REDIS"
    finally:
        cache.delete(key)
