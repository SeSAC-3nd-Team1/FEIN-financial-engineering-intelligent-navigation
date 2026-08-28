"""물방개 읽기 전용 AI Agent API."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
import redis
from sqlalchemy.orm import Session

from app.api.deps import optional_current_user
from app.core.config import settings
from app.core.chat_observability import (
    check_rate_limit,
    new_request_id,
    request_id_context,
)
from app.core.errors import ServiceError
from app.db.session import get_session
from app.integrations.ai.chat_agent_client import (
    AzureOpenAIChatAgentClient,
    ChatAgentClient,
)
from app.models import User
from app.repositories.recommendation import RecommendationRepository
from app.repositories.trading import TradingRepository
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse

router = APIRouter(prefix="/chat", tags=["chat"])


def get_chat_agent_client() -> ChatAgentClient:
    return AzureOpenAIChatAgentClient(
        endpoint=settings.azure_openai_chatbot_endpoint,
        api_key=settings.azure_openai_chatbot_api_key,
        deployment=settings.azure_openai_chatbot_deployment,
        api_version=settings.azure_openai_chatbot_api_version,
        timeout_seconds=settings.ai_chatbot_timeout_seconds,
    )


def _is_personalized_request(payload: ChatMessageRequest) -> bool:
    """개인 계좌·포트폴리오 조회로 이어질 수 있는 요청인지 판별한다."""

    if payload.context.account_id is not None:
        return True
    normalized = " ".join(payload.message.lower().split())
    return any(
        keyword in normalized
        for keyword in (
            "내 계좌",
            "내 포트폴리오",
            "내 자산",
            "내 잔액",
            "내 수익률",
            "내 보유",
            "보유 종목",
            "내 전략",
            "내 투자 전략",
            "내가 선택한 전략",
            "선택한 전략",
        )
    )


def _personalization_fallback(payload: ChatMessageRequest) -> ChatMessageResponse:
    return ChatMessageResponse(
        status="NEEDS_CLARIFICATION",
        text=(
            "개인 계좌 정보는 로그인 후 AI 개인화 동의가 확인된 경우에만 안내할 수 있어요. "
            "현재 화면의 금융 개념이나 서비스 이용 방법은 설명해드릴 수 있습니다."
        ),
        caution="계좌 정보와 투자 판단은 본인 확인 및 제공된 데이터 범위 안에서만 안내합니다.",
        suggested_questions=["PER이 무엇인가요?", "이 화면에서 무엇을 볼 수 있나요?"],
        message_id=str(uuid4()),
        model_version=settings.ai_chatbot_model_version,
        generated_at=datetime.now(UTC),
    )


def _require_personalization_access(
    payload: ChatMessageRequest,
    user: User | None,
    session: Session,
) -> ChatMessageResponse | None:
    if not _is_personalized_request(payload):
        return None
    if user is None:
        return _personalization_fallback(payload)
    if not RecommendationRepository(session).has_ai_personalization_consent(user.id):
        return _personalization_fallback(payload)
    if payload.context.account_id is not None:
        if (
            TradingRepository(session).owned_account(
                payload.context.account_id, user.id
            )
            is None
        ):
            raise ServiceError(
                "ACCOUNT_ACCESS_DENIED",
                "본인 소유 계좌만 조회할 수 있습니다.",
                403,
            )
    return None


@router.post("/messages", response_model=ChatMessageResponse)
async def create_chat_message(
    request: Request,
    response: Response,
    payload: ChatMessageRequest,
    user: User | None = Depends(optional_current_user),
    session: Session = Depends(get_session),
    client: ChatAgentClient = Depends(get_chat_agent_client),
) -> ChatMessageResponse:
    request_id = request.headers.get("X-Request-ID") or new_request_id()
    token = request_id_context.set(request_id)
    response.headers["X-Request-ID"] = request_id
    try:
        client_ip = request.client.host if request.client else "unknown"
        limiter = redis.from_url(settings.redis_url, decode_responses=True)
        user_key = f"user:{user.id}" if user else f"ip:{client_ip}"
        if not check_rate_limit(
            limiter,
            key=user_key,
            limit=settings.ai_chatbot_rate_limit_per_minute,
            window_seconds=settings.ai_chatbot_rate_limit_window_seconds,
        ):
            raise ServiceError(
                "CHAT_AGENT_RATE_LIMITED",
                "챗봇 요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
                429,
            )
        fallback = _require_personalization_access(payload, user, session)
        if fallback is not None:
            return fallback
        # Provider에는 사용자 식별자나 account_id를 전달하지 않는다.
        provider_context = payload.context.model_copy(update={"account_id": None})
        if isinstance(client, AzureOpenAIChatAgentClient):
            result = await client.answer_with_tools(
                payload.message,
                payload.history,
                provider_context,
                session=session,
                user_id=user.id if user else None,
                account_id=payload.context.account_id,
            )
        else:
            result = await client.answer(
                payload.message, payload.history, provider_context
            )
        return ChatMessageResponse(
            **result.model_dump(),
            message_id=str(uuid4()),
            model_version=settings.ai_chatbot_model_version,
            generated_at=datetime.now(UTC),
        )
    finally:
        request_id_context.reset(token)
