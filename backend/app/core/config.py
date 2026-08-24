"""환경변수 기반 애플리케이션 설정."""

from dataclasses import dataclass
from decimal import Decimal
import os


def _required_database_url() -> str:
    """필수 DATABASE_URL을 읽고 누락되면 애플리케이션 시작 전에 실패한다."""

    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL is required")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str = _required_database_url()
    database_connect_timeout_seconds: int = int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "5"))
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    jwt_secret: str = os.getenv("JWT_SECRET", "local-development-only-change-me")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
    initial_cash: Decimal = Decimal(os.getenv("VIRTUAL_ACCOUNT_INITIAL_CASH", "10000000"))
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    ai_profile_timeout_seconds: float = float(os.getenv("AI_PROFILE_TIMEOUT_SECONDS", "15"))
    kis_app_key: str = os.getenv("KIS_APP_KEY", "")
    kis_app_secret: str = os.getenv("KIS_APP_SECRET", "")
    kis_base_url: str = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
    kis_websocket_url: str = os.getenv("KIS_WEBSOCKET_URL", "ws://ops.koreainvestment.com:21000")
    price_cache_ttl_seconds: int = int(os.getenv("PRICE_CACHE_TTL_SECONDS", "5"))
    minute_candle_cache_ttl_seconds: int = int(os.getenv("MINUTE_CANDLE_CACHE_TTL_SECONDS", "15"))
    request_timeout_seconds: float = float(os.getenv("KIS_TIMEOUT_SECONDS", "3"))
    realtime_price_cache_ttl_seconds: int = int(os.getenv("REALTIME_PRICE_CACHE_TTL_SECONDS", "30"))
    realtime_price_stale_seconds: int = int(os.getenv("REALTIME_PRICE_STALE_SECONDS", "10"))
    realtime_reconnect_max_seconds: int = int(os.getenv("KIS_REALTIME_RECONNECT_MAX_SECONDS", "30"))
    realtime_client_queue_size: int = int(os.getenv("KIS_REALTIME_CLIENT_QUEUE_SIZE", "100"))
    realtime_max_symbols_per_client: int = int(os.getenv("KIS_REALTIME_MAX_SYMBOLS_PER_CLIENT", "20"))
    naver_api_hub_client_id: str = os.getenv("NAVER_API_HUB_CLIENT_ID", "")
    naver_api_hub_client_secret: str = os.getenv("NAVER_API_HUB_CLIENT_SECRET", "")
    naver_news_base_url: str = os.getenv("NAVER_NEWS_BASE_URL", "https://naverapihub.apigw.ntruss.com")
    news_search_query: str = os.getenv("NEWS_SEARCH_QUERY", "증시")
    news_cache_ttl_seconds: int = int(os.getenv("NEWS_CACHE_TTL_SECONDS", "300"))
    news_request_timeout_seconds: float = float(os.getenv("NEWS_REQUEST_TIMEOUT_SECONDS", "5"))


settings = Settings()
