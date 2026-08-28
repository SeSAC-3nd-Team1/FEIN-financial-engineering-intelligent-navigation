"""물방개 읽기 전용 AI Agent API."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import optional_current_user
from app.core.config import settings
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
        )
    )


def _require_personalization_access(
    payload: ChatMessageRequest,
    user: User | None,
    session: Session,
) -> None:
    if not _is_personalized_request(payload):
        return
    if user is None:
        raise ServiceError(
            "AUTHENTICATION_REQUIRED",
            "내 계좌와 포트폴리오를 확인하려면 로그인이 필요합니다.",
            401,
        )
    if not RecommendationRepository(session).has_ai_personalization_consent(user.id):
        raise ServiceError(
            "AI_PERSONALIZATION_CONSENT_REQUIRED",
            "개인화된 계좌 안내를 이용하려면 AI 개인화 동의가 필요합니다.",
            403,
        )
    if payload.context.account_id is not None:
        account_id = UUID(payload.context.account_id)
        if TradingRepository(session).owned_account(account_id, user.id) is None:
            raise ServiceError(
                "ACCOUNT_ACCESS_DENIED",
                "본인 소유 계좌만 조회할 수 있습니다.",
                403,
            )


@router.post("/messages", response_model=ChatMessageResponse)
async def create_chat_message(
    payload: ChatMessageRequest,
    user: User | None = Depends(optional_current_user),
    session: Session = Depends(get_session),
    client: ChatAgentClient = Depends(get_chat_agent_client),
) -> ChatMessageResponse:
    _require_personalization_access(payload, user, session)
    # Provider에는 사용자 식별자나 account_id를 전달하지 않는다.
    result = await client.answer(payload.message, payload.history, payload.context)
    return ChatMessageResponse(
        **result.model_dump(),
        message_id=str(uuid4()),
        model_version=settings.ai_chatbot_model_version,
        generated_at=datetime.now(UTC),
    )
