"""환경변수 기반 애플리케이션 설정."""

from dataclasses import dataclass
from decimal import Decimal
import os


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://app:app@postgres:5432/app")
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    jwt_secret: str = os.getenv("JWT_SECRET", "local-development-only-change-me")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
    initial_cash: Decimal = Decimal(os.getenv("VIRTUAL_ACCOUNT_INITIAL_CASH", "10000000"))
    kis_app_key: str = os.getenv("KIS_APP_KEY", "")
    kis_app_secret: str = os.getenv("KIS_APP_SECRET", "")
    kis_base_url: str = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
    price_cache_ttl_seconds: int = int(os.getenv("PRICE_CACHE_TTL_SECONDS", "5"))
    request_timeout_seconds: float = float(os.getenv("KIS_TIMEOUT_SECONDS", "3"))
    naver_api_hub_client_id: str = os.getenv("NAVER_API_HUB_CLIENT_ID", "")
    naver_api_hub_client_secret: str = os.getenv("NAVER_API_HUB_CLIENT_SECRET", "")
    naver_news_base_url: str = os.getenv("NAVER_NEWS_BASE_URL", "https://naverapihub.apigw.ntruss.com")
    news_search_query: str = os.getenv("NEWS_SEARCH_QUERY", "증시")
    news_cache_ttl_seconds: int = int(os.getenv("NEWS_CACHE_TTL_SECONDS", "300"))
    news_request_timeout_seconds: float = float(os.getenv("NEWS_REQUEST_TIMEOUT_SECONDS", "5"))


settings = Settings()
