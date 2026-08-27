from types import SimpleNamespace

import httpx
import pytest
import respx

from agent_orchestration.clients.responses import ResponsesAgentClient
from agent_orchestration.contracts import AgentRequest


class FakeCredential:
    async def get_token(self, *scopes, **kwargs):
        return SimpleNamespace(token="test-token")


@pytest.mark.asyncio
@respx.mock
async def test_responses_client_uses_entra_bearer_and_parses_report():
    endpoint = "https://example.invalid/agents/News/endpoint/protocols/openai/responses"
    route = respx.post(endpoint).mock(
        return_value=httpx.Response(
            200,
            json={
                "output_text": '{"agent":"News","status":"OK","confidence":0.9}'
            },
        )
    )
    async with httpx.AsyncClient() as http:
        client = ResponsesAgentClient(endpoint, FakeCredential(), http)
        report = await client.invoke(
            AgentRequest(request_id="req-1", role="News", user_query="삼성전자 뉴스"),
            timeout_seconds=5,
            idempotency_key="idem-1",
        )

    assert report.agent == "News"
    assert route.calls[0].request.headers["Authorization"] == "Bearer test-token"
    assert route.calls[0].request.headers["Idempotency-Key"] == "idem-1"
