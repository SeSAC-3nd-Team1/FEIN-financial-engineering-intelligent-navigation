"""Config-driven ingress bridge from external chatbots to MBGCoordinator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from agent_orchestration.contracts import AgentRequest


SENSITIVE_CONTEXT_KEYS = frozenset(
    {
        "access_token",
        "account_number",
        "api_key",
        "authorization",
        "broker_credentials",
        "connection_string",
        "credential",
        "password",
        "refresh_token",
        "secret",
        "token",
    }
)


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in SENSITIVE_CONTEXT_KEYS
            or _contains_sensitive_key(nested)
            for key, nested in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_sensitive_key(item) for item in value)
    return False


class ChatbotConfigurationError(ValueError):
    pass


class ChatbotNotRegisteredError(LookupError):
    pass


class ChatbotDisabledError(PermissionError):
    pass


class TextAgentClient(Protocol):
    async def invoke_text(
        self,
        request: AgentRequest,
        *,
        timeout_seconds: float,
        idempotency_key: str,
    ) -> str: ...


class ChatbotRegistration(BaseModel):
    """Non-secret metadata and limits for one chatbot ingress channel."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chatbot_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$")
    display_name: str = Field(min_length=1, max_length=100)
    provider: Literal["internal", "foundry", "http"] = "internal"
    source_agent_name: str | None = Field(default=None, min_length=1, max_length=100)
    source_endpoint: AnyHttpUrl | None = None
    enabled: bool = True
    allowed_context_keys: tuple[str, ...] = ()
    max_input_chars: int = Field(default=4000, ge=1, le=20000)
    max_response_chars: int = Field(default=8000, ge=256, le=32000)
    timeout_seconds: float = Field(default=120, ge=1, le=180)

    @field_validator("allowed_context_keys")
    @classmethod
    def reject_sensitive_context_keys(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(key.strip() for key in value if key.strip()))
        blocked = SENSITIVE_CONTEXT_KEYS.intersection(key.lower() for key in normalized)
        if blocked:
            raise ValueError("sensitive context keys cannot be allowlisted")
        return normalized

    @model_validator(mode="after")
    def validate_provider_metadata(self) -> "ChatbotRegistration":
        if self.provider == "foundry" and not self.source_agent_name:
            raise ValueError("foundry chatbot registration requires source_agent_name")
        if self.provider == "http" and self.source_endpoint is None:
            raise ValueError("http chatbot registration requires source_endpoint")
        if self.source_endpoint is not None and self.source_endpoint.scheme != "https":
            raise ValueError("chatbot source_endpoint must use HTTPS")
        return self


class ChatbotRegistryDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chatbots: list[ChatbotRegistration]


class ChatbotRegistry:
    def __init__(self, registrations: list[ChatbotRegistration]) -> None:
        by_id: dict[str, ChatbotRegistration] = {}
        for registration in registrations:
            if registration.chatbot_id in by_id:
                raise ChatbotConfigurationError(
                    f"duplicate chatbot_id: {registration.chatbot_id}"
                )
            by_id[registration.chatbot_id] = registration
        self._registrations = by_id

    @classmethod
    def from_json(cls, raw: str) -> "ChatbotRegistry":
        try:
            document = ChatbotRegistryDocument.model_validate_json(raw)
        except (ValueError, TypeError) as error:
            raise ChatbotConfigurationError("chatbot registry JSON is invalid") from error
        return cls(document.chatbots)

    @classmethod
    def load(
        cls,
        *,
        path: Path | None = None,
        inline_json: str | None = None,
    ) -> "ChatbotRegistry":
        if path is not None and inline_json:
            raise ChatbotConfigurationError(
                "configure CHATBOT_REGISTRY_PATH or CHATBOT_REGISTRY_JSON, not both"
            )
        if inline_json:
            return cls.from_json(inline_json)
        if path is not None:
            try:
                return cls.from_json(path.read_text(encoding="utf-8"))
            except OSError as error:
                raise ChatbotConfigurationError("chatbot registry file is unavailable") from error
        raise ChatbotConfigurationError("chatbot registry is not configured")

    def require_enabled(self, chatbot_id: str) -> ChatbotRegistration:
        registration = self._registrations.get(chatbot_id)
        if registration is None:
            raise ChatbotNotRegisteredError("chatbot is not registered")
        if not registration.enabled:
            raise ChatbotDisabledError("chatbot is disabled")
        return registration


class ChatbotMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chatbot_id: str
    message: str = Field(min_length=1)
    request_id: str | None = None
    conversation_id: str | None = Field(default=None, max_length=200)
    ticker: str | None = Field(default=None, pattern=r"^[0-9A-Za-z._-]{1,20}$")
    company_name: str | None = Field(default=None, max_length=100)
    context: dict[str, Any] = Field(default_factory=dict)


class ChatbotReply(BaseModel):
    request_id: str
    chatbot_id: str
    coordinator: Literal["MBGCoordinator"] = "MBGCoordinator"
    output_text: str
    truncated: bool = False
    execution_allowed: Literal[False] = False


class MBGChatbotBridge:
    """Authorize one registered channel and forward its message to MBGCoordinator."""

    def __init__(self, coordinator: TextAgentClient, registry: ChatbotRegistry) -> None:
        self._coordinator = coordinator
        self._registry = registry

    async def handle(self, message: ChatbotMessage) -> ChatbotReply:
        registration = self._registry.require_enabled(message.chatbot_id)
        if len(message.message) > registration.max_input_chars:
            raise ValueError("chatbot message exceeds configured max_input_chars")

        if _contains_sensitive_key(message.context):
            raise ValueError("chatbot context contains a sensitive key")

        allowed_context = {
            key: value
            for key, value in message.context.items()
            if key in registration.allowed_context_keys
            and key.lower() not in SENSITIVE_CONTEXT_KEYS
        }
        request_id = message.request_id or str(uuid4())
        request = AgentRequest(
            request_id=request_id,
            role="MBGCoordinator",
            user_query=message.message,
            ticker=message.ticker,
            company_name=message.company_name,
            context={
                "chatbot_channel": {
                    "chatbot_id": registration.chatbot_id,
                    "display_name": registration.display_name,
                    "provider": registration.provider,
                    "source_agent_name": registration.source_agent_name,
                    "conversation_id": message.conversation_id,
                },
                "channel_context": allowed_context,
                "execution_allowed": False,
                "input_trust": "UNTRUSTED_CHATBOT_CHANNEL",
            },
        )
        output_text = await self._coordinator.invoke_text(
            request,
            timeout_seconds=registration.timeout_seconds,
            idempotency_key=f"{request_id}:chatbot:{registration.chatbot_id}",
        )
        truncated = len(output_text) > registration.max_response_chars
        if truncated:
            output_text = output_text[: registration.max_response_chars]
        return ChatbotReply(
            request_id=request_id,
            chatbot_id=registration.chatbot_id,
            output_text=output_text,
            truncated=truncated,
        )
