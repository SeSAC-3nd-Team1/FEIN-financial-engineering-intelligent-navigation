from datetime import datetime
import hashlib
import logging

import httpx
import pytest

from app.core.errors import ServiceError
from app.integrations.naver.news_client import NaverNewsClient


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None, json_error: Exception | None = None) -> None:
        self.status_code = status_code
        self.payload = payload
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


def provider_payload(**item_overrides) -> dict:
    item = {
        "title": "<b>삼성전자</b> &amp; 반도체 상승",
        "originallink": "https://www.hankyung.com/article/123",
        "link": "https://n.news.naver.com/article/001/123",
        "description": "&quot;외국인 순매수&quot;가 <b>증가</b>했습니다.",
        "pubDate": "Sat, 23 Aug 2026 15:42:00 +0900",
    }
    item.update(item_overrides)
    return {
        "lastBuildDate": "Sat, 23 Aug 2026 15:50:00 +0900",
        "total": 1234,
        "start": 1,
        "display": 1,
        "items": [item],
    }


def client() -> NaverNewsClient:
    return NaverNewsClient(
        client_id="test-id",
        client_secret="test-secret",
        base_url="https://naver.example",
        timeout_seconds=2,
    )


def test_search_normalizes_html_entities_link_date_publisher_and_stable_id(monkeypatch) -> None:
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse(payload=provider_payload())

    monkeypatch.setattr("app.integrations.naver.news_client.httpx.get", fake_get)
    result = client().search("증시", page=2, size=20)
    article = result.items[0]

    assert captured["url"] == "https://naver.example/search/v1/news"
    assert captured["params"] == {"query": "증시", "display": 20, "start": 21, "sort": "date"}
    assert captured["headers"] == {
        "X-NCP-APIGW-API-KEY-ID": "test-id",
        "X-NCP-APIGW-API-KEY": "test-secret",
    }
    assert article.title == "삼성전자 & 반도체 상승"
    assert article.summary == '"외국인 순매수"가 증가했습니다.'
    assert article.link == "https://www.hankyung.com/article/123"
    assert article.publisher == "hankyung.com"
    assert article.thumbnail is None
    assert article.id == hashlib.sha256(article.link.encode()).hexdigest()[:24]
    assert article.published_at.isoformat() == "2026-08-23T15:42:00+09:00"
    assert isinstance(result.updated_at, datetime)
    assert result.total_count == 1234


def test_originallink_missing_uses_naver_link(monkeypatch) -> None:
    payload = provider_payload(originallink="")
    monkeypatch.setattr(
        "app.integrations.naver.news_client.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(payload=payload),
    )

    article = client().search("증시", 1, 1).items[0]
    assert article.link == "https://n.news.naver.com/article/001/123"
    assert article.publisher == "n.news.naver.com"


def test_timeout_returns_unavailable_without_logging_credentials(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        "app.integrations.naver.news_client.httpx.get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ReadTimeout("timeout")),
    )

    with caplog.at_level(logging.WARNING), pytest.raises(ServiceError) as error:
        client().search("증시", 1, 20)

    assert error.value.code == "NAVER_NEWS_UNAVAILABLE"
    assert error.value.status_code == 502
    assert "test-secret" not in caplog.text
    assert "test-id" not in caplog.text


@pytest.mark.parametrize(
    ("status", "code", "http_status"),
    [(429, "NAVER_NEWS_RATE_LIMIT", 503), (500, "NAVER_NEWS_UNAVAILABLE", 502)],
)
def test_provider_http_errors(monkeypatch, status, code, http_status) -> None:
    monkeypatch.setattr(
        "app.integrations.naver.news_client.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(status_code=status, payload={}),
    )

    with pytest.raises(ServiceError) as error:
        client().search("증시", 1, 20)
    assert error.value.code == code
    assert error.value.status_code == http_status


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(payload={"total": 1, "lastBuildDate": "bad", "items": "not-list"}),
        FakeResponse(payload=provider_payload(pubDate="not-a-date")),
        FakeResponse(json_error=ValueError("malformed json")),
    ],
)
def test_malformed_provider_response(monkeypatch, response) -> None:
    monkeypatch.setattr(
        "app.integrations.naver.news_client.httpx.get",
        lambda *_args, **_kwargs: response,
    )

    with pytest.raises(ServiceError) as error:
        client().search("증시", 1, 20)
    assert error.value.code == "NAVER_NEWS_UNAVAILABLE"


def test_missing_credentials_fails_before_http(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.integrations.naver.news_client.httpx.get",
        lambda *_args, **_kwargs: pytest.fail("HTTP must not be called"),
    )
    with pytest.raises(ServiceError) as error:
        NaverNewsClient(client_id="", client_secret="").search("증시", 1, 20)
    assert error.value.code == "NAVER_NEWS_NOT_CONFIGURED"
    assert error.value.status_code == 503
