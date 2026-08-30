from types import SimpleNamespace

import pytest

from agent_orchestration.clients.foundry_sdk import FoundrySDKAgentClient
from agent_orchestration.contracts import AgentRequest
from agent_orchestration.layers import LayerController


class Conversations:
    def __init__(self):
        self.deleted = []

    async def create(self):
        return SimpleNamespace(id="conversation-1")

    async def delete(self, *, conversation_id):
        self.deleted.append(conversation_id)


class Responses:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            output_text='{"agent":"News","request_id":"req-1","status":"OK","confidence":0.8}'
        )


class OpenAIClient:
    def __init__(self):
        self.conversations = Conversations()
        self.responses = Responses()


class MinimalResponses(Responses):
    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            output_text=(
                '{"request_id":"req-1","status":"ok",'
                '"message":"reachable","execution_allowed":false}'
            )
        )


@pytest.mark.asyncio
async def test_sdk_client_uses_agent_reference_and_deletes_request_conversation():
    openai = OpenAIClient()
    client = FoundrySDKAgentClient(
        openai, "News", LayerController().profile_for("News")
    )

    result = await client.invoke(
        AgentRequest(request_id="req-1", role="News", user_query="삼성전자 뉴스"),
        timeout_seconds=5,
        idempotency_key="idem-1",
    )

    assert result.agent == "News"
    assert openai.responses.kwargs["extra_body"] == {
        "agent_reference": {"name": "News", "type": "agent_reference"}
    }
    assert openai.responses.kwargs["extra_headers"]["Idempotency-Key"] == "idem-1"
    assert "runtime_layers" in openai.responses.kwargs["input"]
    assert openai.conversations.deleted == ["conversation-1"]


@pytest.mark.asyncio
async def test_sdk_client_normalizes_minimal_foundry_agent_response():
    openai = OpenAIClient()
    openai.responses = MinimalResponses()
    client = FoundrySDKAgentClient(
        openai, "FinancialReport", LayerController().profile_for("FinancialReport")
    )

    result = await client.invoke(
        AgentRequest(
            request_id="req-1",
            role="FinancialReport",
            user_query="연결 점검",
        ),
        timeout_seconds=5,
        idempotency_key="idem-1",
    )

    assert result.agent == "FinancialReport"
    assert result.status == "OK"
    assert result.summary == "reachable"
    assert result.details["execution_allowed"] is False
