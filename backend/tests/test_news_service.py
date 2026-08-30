from datetime import UTC, datetime

import redis

from app.schemas.api import NewsArticleResponse, NewsListResponse
from app.services.news import NewsService


def news_result() -> NewsListResponse:
    return NewsListResponse(
        items=[NewsArticleResponse(
            id="stable-id",
            title="증시 뉴스",
            summary="요약",
            publisher="example.com",
            publishedAt=datetime(2026, 8, 23, tzinfo=UTC),
            link="https://example.com/news/1",
        )],
        totalCount=1,
        updatedAt=datetime(2026, 8, 23, tzinfo=UTC),
    )


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, page: int, size: int) -> NewsListResponse:
        self.calls += 1
        assert (query, page, size) == ("증시", 1, 20)
        return news_result()


class FakeCache:
    def __init__(self, cached: str | None = None, *, fail_get=False, fail_set=False) -> None:
        self.cached = cached
        self.fail_get = fail_get
        self.fail_set = fail_set
        self.set_calls: list[tuple[str, int, str]] = []

    def get(self, _key: str) -> str | None:
        if self.fail_get:
            raise redis.ConnectionError("get failed")
        return self.cached

    def setex(self, key: str, ttl: int, value: str) -> None:
        if self.fail_set:
            raise redis.ConnectionError("set failed")
        self.set_calls.append((key, ttl, value))
        self.cached = value


def test_cache_hit_skips_naver_client() -> None:
    client = FakeClient()
    cache = FakeCache(news_result().model_dump_json(by_alias=True))
    result = NewsService(client=client, cache=cache).get_korean_news(1, 20)

    assert result.items[0].id == "stable-id"
    assert client.calls == 0


def test_cache_miss_calls_client_and_sets_ttl() -> None:
    client = FakeClient()
    cache = FakeCache()
    service = NewsService(client=client, cache=cache)

    first = service.get_korean_news(1, 20)
    second = service.get_korean_news(1, 20)

    assert first.items[0].id == second.items[0].id == "stable-id"
    assert client.calls == 1
    assert cache.set_calls[0][0] == "information:news:kr:증시:1:20"
    assert cache.set_calls[0][1] == 300


def test_redis_get_failure_falls_back_to_naver() -> None:
    client = FakeClient()
    result = NewsService(client=client, cache=FakeCache(fail_get=True)).get_korean_news(1, 20)
    assert result.total_count == 1
    assert client.calls == 1


def test_redis_set_failure_still_returns_news() -> None:
    client = FakeClient()
    result = NewsService(client=client, cache=FakeCache(fail_set=True)).get_korean_news(1, 20)
    assert result.items[0].title == "증시 뉴스"
    assert client.calls == 1
