"""물방개 읽기 전용 AI Agent 요청/응답 계약."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID


class ChatHistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatScreenContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screen: str = Field(min_length=1, max_length=50)
    stock_code: str | None = Field(default=None, pattern=r"^[0-9A-Z]{6,12}$")
    strategy_id: str | None = Field(default=None, min_length=1, max_length=30)
    account_id: UUID | None = None


class ChatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=10)
    context: ChatScreenContext


class ChatAgentResult(BaseModel):
    """Provider가 JSON Schema에 맞춰 생성해야 하는 안전한 답변."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["COMPLETED", "NEEDS_CLARIFICATION", "REFUSED"]
    text: str = Field(min_length=1, max_length=2000)
    # Azure Structured Outputs의 strict schema는 모든 property가 required여야 한다.
    # 값 부재는 nullable/빈 배열로 표현하되 필드 자체는 항상 모델이 반환한다.
    caution: str | None = Field(max_length=500)
    suggested_questions: list[str] = Field(max_length=3)


class ChatMessageResponse(ChatAgentResult):
    message_id: str
    model_version: str
    generated_at: datetime
