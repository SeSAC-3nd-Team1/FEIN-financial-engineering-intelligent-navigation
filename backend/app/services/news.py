"""NAVER 금융 뉴스의 Redis page cache와 provider fallback을 관리한다."""

import logging

from pydantic import ValidationError
import redis

from app.core.config import settings
from app.integrations.naver import NaverNewsClient
from app.schemas.api import NewsListResponse

logger = logging.getLogger(__name__)


class NewsService:
    def __init__(self, client: NaverNewsClient | None = None, cache: redis.Redis | None = None) -> None:
        self.client = client or NaverNewsClient()
        self.cache = cache or redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
        )

    def get_korean_news(self, page: int, size: int) -> NewsListResponse:
        query = settings.news_search_query
        key = f"information:news:kr:{query}:{page}:{size}"
        try:
            cached = self.cache.get(key)
            if cached:
                return NewsListResponse.model_validate_json(cached)
        except (redis.RedisError, ValidationError, ValueError):
            logger.warning("Redis news cache read failed page=%s size=%s", page, size)

        result = self.client.search(query, page, size)
        try:
            self.cache.setex(
                key,
                settings.news_cache_ttl_seconds,
                result.model_dump_json(by_alias=True),
            )
        except redis.RedisError:
            logger.warning("Redis news cache write failed page=%s size=%s", page, size)
        return result
