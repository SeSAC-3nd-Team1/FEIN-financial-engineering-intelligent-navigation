import pytest

from app.core.errors import ServiceError
from app.integrations.ai.foundry_orchestration_chat_agent_client import (
    FoundryOrchestrationChatAgentClient,
)
from app.schemas.chat import ChatScreenContext


REGISTRY = (
    '{"chatbots":[{"chatbot_id":"fein-web-chatbot",'
    '"display_name":"FE!N Web Chatbot","provider":"foundry",'
    '"source_agent_name":"MBGCoordinator","enabled":true,'
    '"allowed_context_keys":["screen","stock_code","strategy_id","verified_personal_summary"],'
    '"max_input_chars":4000,"max_response_chars":8000,"timeout_seconds":120}]}'
)


def test_public_context_only_contains_verified_fields() -> None:
    context = ChatScreenContext(screen="stock", stock_code="005930")

    assert FoundryOrchestrationChatAgentClient._public_context(context) == {
        "screen": "stock",
        "stock_code": "005930",
    }


def test_public_context_can_include_verified_personal_summary() -> None:
    context = ChatScreenContext(screen="portfolio")
    summary = {"total_assets": 1000, "source": "virtual_accounts"}

    result = FoundryOrchestrationChatAgentClient._public_context(context, summary)

    assert result["verified_personal_summary"] == summary
    assert "account_id" not in result


@pytest.mark.asyncio
async def test_empty_registry_is_mapped_to_configuration_error() -> None:
    client = FoundryOrchestrationChatAgentClient(
        project_endpoint="https://example.invalid/api/projects/test",
        agent_names={},
        registry_json="",
        chatbot_id="fein-web-chatbot",
        timeout_seconds=1,
    )

    with pytest.raises(ServiceError) as error:
        await client.answer("PER이 뭐야?", [], ChatScreenContext(screen="home"))

    assert error.value.code == "CHAT_AGENT_NOT_CONFIGURED"


def test_registry_fixture_is_valid_for_the_expected_chatbot() -> None:
    client = FoundryOrchestrationChatAgentClient(
        project_endpoint="https://example.invalid/api/projects/test",
        agent_names={},
        registry_json=REGISTRY,
        chatbot_id="fein-web-chatbot",
        timeout_seconds=1,
    )

    assert client.chatbot_id == "fein-web-chatbot"
