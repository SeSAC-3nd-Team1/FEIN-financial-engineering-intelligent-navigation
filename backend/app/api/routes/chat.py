"""물방개 읽기 전용 AI Agent API."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends

from app.api.deps import current_user
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
    _: User = Depends(current_user),
    client: ChatAgentClient = Depends(get_chat_agent_client),
) -> ChatMessageResponse:
    # 로그인 사용자만 호출할 수 있으며 사용자 식별값은 Provider에 전달하지 않는다.
    result = await client.answer(payload.message, payload.history, payload.context)
    return ChatMessageResponse(
        **result.model_dump(),
        message_id=str(uuid4()),
        model_version=settings.ai_chatbot_model_version,
        generated_at=datetime.now(UTC),
    )
