import json

import pytest

from agent_orchestration.chatbot_bridge import (
    ChatbotConfigurationError,
    ChatbotDisabledError,
    ChatbotMessage,
    ChatbotNotRegisteredError,
    ChatbotRegistration,
    ChatbotRegistry,
    MBGChatbotBridge,
)


class FakeCoordinator:
    def __init__(self, output: str = "MBG response") -> None:
        self.output = output
        self.request = None
        self.timeout_seconds = None
        self.idempotency_key = None

    async def invoke_text(
        self, request, *, timeout_seconds: float, idempotency_key: str
    ) -> str:
        self.request = request
        self.timeout_seconds = timeout_seconds
        self.idempotency_key = idempotency_key
        return self.output


def registration(**updates) -> ChatbotRegistration:
    values = {
        "chatbot_id": "service-chatbot",
        "display_name": "Service Chatbot",
        "provider": "foundry",
        "source_agent_name": "ConfiguredChatbotAgent",
        "allowed_context_keys": ["locale", "channel"],
        "timeout_seconds": 45,
    }
    values.update(updates)
    return ChatbotRegistration.model_validate(values)


@pytest.mark.asyncio
async def test_registered_chatbot_forwards_allowlisted_context_to_mbg():
    coordinator = FakeCoordinator()
    bridge = MBGChatbotBridge(
        coordinator, ChatbotRegistry([registration()])
    )

    reply = await bridge.handle(
        ChatbotMessage(
            chatbot_id="service-chatbot",
            request_id="request-1",
            conversation_id="conversation-1",
            message="삼성전자를 분석해줘",
            ticker="005930",
            company_name="삼성전자",
            context={"locale": "ko-KR", "channel": "web", "ignored": "drop"},
        )
    )

    assert reply.output_text == "MBG response"
    assert reply.execution_allowed is False
    assert coordinator.request.role == "MBGCoordinator"
    assert coordinator.request.context["channel_context"] == {
        "locale": "ko-KR",
        "channel": "web",
    }
    assert coordinator.request.context["execution_allowed"] is False
    assert coordinator.timeout_seconds == 45
    assert coordinator.idempotency_key == "request-1:chatbot:service-chatbot"


@pytest.mark.asyncio
async def test_bridge_rejects_unknown_and_disabled_chatbots():
    bridge = MBGChatbotBridge(
        FakeCoordinator(),
        ChatbotRegistry([registration(enabled=False)]),
    )

    with pytest.raises(ChatbotNotRegisteredError):
        await bridge.handle(ChatbotMessage(chatbot_id="unknown", message="hello"))
    with pytest.raises(ChatbotDisabledError):
        await bridge.handle(
            ChatbotMessage(chatbot_id="service-chatbot", message="hello")
        )


@pytest.mark.asyncio
async def test_bridge_enforces_input_and_output_limits():
    coordinator = FakeCoordinator(output="x" * 300)
    bridge = MBGChatbotBridge(
        coordinator,
        ChatbotRegistry(
            [registration(max_input_chars=3, max_response_chars=256)]
        ),
    )

    with pytest.raises(ValueError, match="max_input_chars"):
        await bridge.handle(
            ChatbotMessage(chatbot_id="service-chatbot", message="1234")
        )

    reply = await bridge.handle(
        ChatbotMessage(chatbot_id="service-chatbot", message="123")
    )
    assert reply.truncated is True
    assert len(reply.output_text) == 256


@pytest.mark.asyncio
async def test_bridge_rejects_nested_sensitive_context():
    bridge = MBGChatbotBridge(
        FakeCoordinator(), ChatbotRegistry([registration()])
    )

    with pytest.raises(ValueError, match="sensitive"):
        await bridge.handle(
            ChatbotMessage(
                chatbot_id="service-chatbot",
                message="hello",
                context={"channel": {"access_token": "do-not-forward"}},
            )
        )


def test_registry_loads_from_json_without_code_changes():
    raw = json.dumps(
        {
            "chatbots": [
                {
                    "chatbot_id": "another-chatbot",
                    "display_name": "Another Chatbot",
                    "provider": "http",
                    "source_endpoint": "https://chatbot.example.test/responses",
                }
            ]
        }
    )

    registry = ChatbotRegistry.from_json(raw)

    assert registry.require_enabled("another-chatbot").provider == "http"


@pytest.mark.parametrize(
    "values",
    [
        {"provider": "foundry", "source_agent_name": None},
        {"provider": "http", "source_endpoint": None},
        {"provider": "http", "source_endpoint": "http://chatbot.example.test"},
        {"allowed_context_keys": ["locale", "access_token"]},
    ],
)
def test_registration_rejects_incomplete_or_sensitive_configuration(values):
    with pytest.raises(ValueError):
        registration(**values)


def test_registry_rejects_duplicate_ids_and_ambiguous_sources(tmp_path):
    one = registration()
    with pytest.raises(ChatbotConfigurationError, match="duplicate"):
        ChatbotRegistry([one, one])

    path = tmp_path / "chatbots.json"
    path.write_text('{"chatbots": []}', encoding="utf-8")
    with pytest.raises(ChatbotConfigurationError, match="not both"):
        ChatbotRegistry.load(path=path, inline_json='{"chatbots": []}')
