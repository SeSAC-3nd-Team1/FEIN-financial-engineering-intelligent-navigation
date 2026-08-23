"""명시적으로 활성화할 때만 실제 NAVER API HUB 뉴스→Redis 경로를 확인한다."""

import os

import pytest
import redis

from app.core.config import settings
from app.services.news import NewsService

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_NAVER_NEWS_INTEGRATION") != "1",
    reason="RUN_NAVER_NEWS_INTEGRATION=1 required",
)


def test_live_naver_news_is_cached_without_persistence() -> None:
    if not settings.naver_api_hub_client_id or not settings.naver_api_hub_client_secret:
        pytest.skip("NAVER API HUB credentials are required")

    page, size = 1, 1
    key = f"information:news:kr:{settings.news_search_query}:{page}:{size}"
    cache = redis.from_url(settings.redis_url, decode_responses=True)
    cache.delete(key)
    try:
        first = NewsService(cache=cache).get_korean_news(page, size)
        assert first.items
        assert first.items[0].title
        assert first.items[0].link.startswith(("http://", "https://"))
        assert first.items[0].published_at.tzinfo is not None
        ttl = cache.ttl(key)
        assert 0 < ttl <= settings.news_cache_ttl_seconds

        second = NewsService(cache=cache).get_korean_news(page, size)
        assert second.items[0].id == first.items[0].id
    finally:
        cache.delete(key)
