from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.routes.information import get_news_service
from app.core.errors import ServiceError
from app.main import app
from app.schemas.api import NewsArticleResponse, NewsListResponse


class FakeNewsService:
    def __init__(self, error: ServiceError | None = None) -> None:
        self.error = error
        self.calls: list[tuple[int, int]] = []

    def get_korean_news(self, page: int, size: int) -> NewsListResponse:
        self.calls.append((page, size))
        if self.error:
            raise self.error
        now = datetime(2026, 8, 23, tzinfo=UTC)
        return NewsListResponse(
            items=[NewsArticleResponse(
                id="news-id",
                title="제목",
                summary="요약",
                publisher="example.com",
                publishedAt=now,
                link="https://example.com/news",
            )],
            totalCount=1,
            updatedAt=now,
        )


def test_news_api_default_pagination_and_response_contract() -> None:
    service = FakeNewsService()
    app.dependency_overrides[get_news_service] = lambda: service
    try:
        response = TestClient(app).get("/api/v1/information/news/kr")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert service.calls == [(1, 20)]
    assert response.json() == {
        "items": [{
            "id": "news-id",
            "title": "제목",
            "summary": "요약",
            "thumbnail": None,
            "publisher": "example.com",
            "publishedAt": "2026-08-23T00:00:00Z",
            "link": "https://example.com/news",
        }],
        "totalCount": 1,
        "updatedAt": "2026-08-23T00:00:00Z",
    }


def test_news_api_provider_error_contract() -> None:
    service = FakeNewsService(ServiceError("NAVER_NEWS_UNAVAILABLE", "뉴스 장애", 502))
    app.dependency_overrides[get_news_service] = lambda: service
    try:
        response = TestClient(app).get("/api/v1/information/news/kr")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 502
    assert response.json() == {"code": "NAVER_NEWS_UNAVAILABLE", "message": "뉴스 장애"}


def test_news_api_custom_pagination() -> None:
    service = FakeNewsService()
    app.dependency_overrides[get_news_service] = lambda: service
    try:
        response = TestClient(app).get("/api/v1/information/news/kr?page=2&size=50")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert service.calls == [(2, 50)]


def test_news_api_accepts_maximum_provider_start() -> None:
    service = FakeNewsService()
    app.dependency_overrides[get_news_service] = lambda: service
    try:
        response = TestClient(app).get("/api/v1/information/news/kr?page=1000&size=1")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert service.calls == [(1000, 1)]


def test_news_api_rejects_start_above_provider_limit_before_service_call() -> None:
    service = FakeNewsService()
    app.dependency_overrides[get_news_service] = lambda: service
    try:
        response = TestClient(app).get("/api/v1/information/news/kr?page=51&size=20")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
    assert service.calls == []


def test_news_api_rejects_invalid_pagination() -> None:
    client = TestClient(app)
    for query in ("page=0&size=20", "page=1&size=0", "page=1&size=51"):
        assert client.get(f"/api/v1/information/news/kr?{query}").status_code == 422
