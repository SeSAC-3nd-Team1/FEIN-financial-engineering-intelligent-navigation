"""NAVER API HUB Search News 응답을 서비스 뉴스 계약으로 정규화한다."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import hashlib
from html import unescape
from html.parser import HTMLParser
import logging
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.errors import ServiceError
from app.schemas.api import NewsArticleResponse, NewsListResponse

logger = logging.getLogger(__name__)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_html_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    return unescape("".join(parser.parts)).strip()


def parse_provider_datetime(value: str) -> datetime:
    parsed = parsedate_to_datetime(value)
    if parsed is None:
        raise ValueError("provider datetime is missing")
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


class NaverNewsClient:
    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.client_id = settings.naver_api_hub_client_id if client_id is None else client_id
        self.client_secret = settings.naver_api_hub_client_secret if client_secret is None else client_secret
        self.base_url = (base_url or settings.naver_news_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.news_request_timeout_seconds

    def search(self, query: str, page: int, size: int) -> NewsListResponse:
        if not self.client_id or not self.client_secret:
            raise ServiceError(
                "NAVER_NEWS_NOT_CONFIGURED",
                "NAVER 뉴스 제공자 credential이 설정되지 않았습니다.",
                503,
            )

        try:
            response = httpx.get(
                f"{self.base_url}/search/v1/news",
                headers={
                    "X-NCP-APIGW-API-KEY-ID": self.client_id,
                    "X-NCP-APIGW-API-KEY": self.client_secret,
                },
                params={
                    "query": query,
                    "display": size,
                    "start": ((page - 1) * size) + 1,
                    "sort": "date",
                },
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            logger.warning("NAVER news request timed out")
            raise ServiceError("NAVER_NEWS_UNAVAILABLE", "현재 뉴스를 불러올 수 없습니다.", 502) from exc
        except httpx.HTTPError as exc:
            logger.warning("NAVER news request failed error=%s", type(exc).__name__)
            raise ServiceError("NAVER_NEWS_UNAVAILABLE", "현재 뉴스를 불러올 수 없습니다.", 502) from exc

        if response.status_code == 429:
            raise ServiceError("NAVER_NEWS_RATE_LIMIT", "뉴스 조회 한도를 초과했습니다.", 503)
        if response.status_code >= 400:
            logger.warning("NAVER news provider returned status=%s", response.status_code)
            raise ServiceError("NAVER_NEWS_UNAVAILABLE", "현재 뉴스를 불러올 수 없습니다.", 502)

        try:
            payload = response.json()
            provider_items = payload["items"]
            if not isinstance(provider_items, list):
                raise TypeError("items must be a list")
            items = [self._normalize_item(item) for item in provider_items]
            return NewsListResponse(
                items=items,
                totalCount=int(payload["total"]),
                updatedAt=parse_provider_datetime(payload["lastBuildDate"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("NAVER news response schema is invalid error=%s", type(exc).__name__)
            raise ServiceError("NAVER_NEWS_UNAVAILABLE", "뉴스 응답 형식이 올바르지 않습니다.", 502) from exc

    @staticmethod
    def _normalize_item(item: dict) -> NewsArticleResponse:
        if not isinstance(item, dict):
            raise TypeError("news item must be an object")
        link = (item.get("originallink") or item.get("link") or "").strip()
        if not link:
            raise ValueError("news link is missing")
        hostname = (urlparse(link).hostname or "unknown").lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return NewsArticleResponse(
            id=hashlib.sha256(link.encode("utf-8")).hexdigest()[:24],
            title=clean_html_text(str(item["title"])),
            summary=clean_html_text(str(item["description"])),
            thumbnail=None,
            publisher=hostname,
            publishedAt=parse_provider_datetime(str(item["pubDate"])),
            link=link,
        )
