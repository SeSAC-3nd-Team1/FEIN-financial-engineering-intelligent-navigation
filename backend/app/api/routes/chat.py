"""물방개 읽기 전용 AI Agent API."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends

from app.api.deps import optional_current_user
from app.core.config import settings
from app.integrations.ai.chat_agent_client import AzureOpenAIChatAgentClient, ChatAgentClient
from app.models import User
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


@router.post("/messages", response_model=ChatMessageResponse)
async def create_chat_message(
    payload: ChatMessageRequest,
    _: User | None = Depends(optional_current_user),
    client: ChatAgentClient = Depends(get_chat_agent_client),
) -> ChatMessageResponse:
    # 인증은 선택 사항이다. 현재 1차 Agent에는 개인 계좌 Tool이 없으므로 사용자 식별값을
    # Provider에 전달하지 않고, 공개 금융 설명과 화면 context만 사용한다.
    result = await client.answer(payload.message, payload.history, payload.context)
    return ChatMessageResponse(
        **result.model_dump(),
        message_id=str(uuid4()),
        model_version=settings.ai_chatbot_model_version,
        generated_at=datetime.now(UTC),
    )
