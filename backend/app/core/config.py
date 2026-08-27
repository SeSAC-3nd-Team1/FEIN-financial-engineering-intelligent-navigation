"""환경변수 기반 애플리케이션 설정."""

from dataclasses import dataclass
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
    acs_email_connection_string: str = os.getenv("ACS_EMAIL_CONNECTION_STRING", "").strip()
    acs_email_sender_address: str = os.getenv("ACS_EMAIL_SENDER_ADDRESS", "").strip()
    email_otp_secret: str = os.getenv("EMAIL_OTP_SECRET", "").strip()
    email_otp_ttl_seconds: int = int(os.getenv("EMAIL_OTP_TTL_SECONDS", "300"))
    email_otp_max_attempts: int = int(os.getenv("EMAIL_OTP_MAX_ATTEMPTS", "5"))
    email_otp_resend_seconds: int = int(os.getenv("EMAIL_OTP_RESEND_SECONDS", "60"))
    email_otp_hourly_limit: int = int(os.getenv("EMAIL_OTP_HOURLY_LIMIT", "5"))
    email_otp_ip_hourly_limit: int = int(os.getenv("EMAIL_OTP_IP_HOURLY_LIMIT", "20"))
    email_verification_token_ttl_seconds: int = int(
        os.getenv("EMAIL_VERIFICATION_TOKEN_TTL_SECONDS", "1800")
    )
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    ai_profile_timeout_seconds: float = float(os.getenv("AI_PROFILE_TIMEOUT_SECONDS", "15"))
    ai_profile_model_version: str = os.getenv("AI_PROFILE_MODEL_VERSION", "investor-profile-v1")
    ai_profile_prompt_version: str = os.getenv("AI_PROFILE_PROMPT_VERSION", "v1")
    azure_openai_recommendation_deployment: str = os.getenv("AZURE_OPENAI_RECOMMENDATION_DEPLOYMENT", "")
    ai_recommendation_timeout_seconds: float = float(os.getenv("AI_RECOMMENDATION_TIMEOUT_SECONDS", "15"))
    ai_recommendation_model_version: str = os.getenv("AI_RECOMMENDATION_MODEL_VERSION", "strategy-recommender-v1")
    ai_recommendation_prompt_version: str = os.getenv("AI_RECOMMENDATION_PROMPT_VERSION", "v1")
    ai_recommendation_dataset_version: str = os.getenv("AI_RECOMMENDATION_DATASET_VERSION", "financial-8y-v1")
    azure_openai_rebalancing_deployment: str = os.getenv("AZURE_OPENAI_REBALANCING_DEPLOYMENT", "")
    ai_rebalancing_timeout_seconds: float = float(os.getenv("AI_REBALANCING_TIMEOUT_SECONDS", "15"))
    ai_rebalancing_model_version: str = os.getenv("AI_REBALANCING_MODEL_VERSION", "rebalancing-v1")
    azure_openai_comparison_deployment: str = os.getenv("AZURE_OPENAI_COMPARISON_DEPLOYMENT", "")
    ai_comparison_timeout_seconds: float = float(os.getenv("AI_COMPARISON_TIMEOUT_SECONDS", "15"))
    ai_comparison_model_version: str = os.getenv("AI_COMPARISON_MODEL_VERSION", "portfolio-comparison-v1")
    azure_openai_chatbot_deployment: str = os.getenv("AZURE_OPENAI_CHATBOT_DEPLOYMENT", "")
    ai_chatbot_timeout_seconds: float = float(os.getenv("AI_CHATBOT_TIMEOUT_SECONDS", "30"))
    ai_chatbot_model_version: str = os.getenv("AI_CHATBOT_MODEL_VERSION", "chatbot-v1")
    ai_chatbot_prompt_version: str = os.getenv("AI_CHATBOT_PROMPT_VERSION", "v1")
    strategy_catalog_version: str = os.getenv("STRATEGY_CATALOG_VERSION", "v1")
    kis_app_key: str = os.getenv("KIS_APP_KEY", "")
    kis_app_secret: str = os.getenv("KIS_APP_SECRET", "")
    kis_base_url: str = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
    kis_websocket_url: str = os.getenv("KIS_WEBSOCKET_URL", "ws://ops.koreainvestment.com:21000")
    price_cache_ttl_seconds: int = int(os.getenv("PRICE_CACHE_TTL_SECONDS", "5"))
    minute_candle_cache_ttl_seconds: int = int(os.getenv("MINUTE_CANDLE_CACHE_TTL_SECONDS", "15"))
    request_timeout_seconds: float = float(os.getenv("KIS_TIMEOUT_SECONDS", "3"))
    kis_rest_page_interval_seconds: float = float(os.getenv("KIS_REST_PAGE_INTERVAL_SECONDS", "0.5"))
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

    @property
    def email_verification_configured(self) -> bool:
        """ACS Email과 OTP 서명 설정이 모두 있을 때만 실제 발송을 허용한다."""

        return all(
            (
                self.acs_email_connection_string,
                self.acs_email_sender_address,
                self.email_otp_secret,
            )
        )


settings = Settings()
