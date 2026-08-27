import json
import traceback
from types import SimpleNamespace

import httpx
import pytest
import respx
from azure.core.exceptions import ClientAuthenticationError

from agent_orchestration.clients.responses import AgentClientError, ResponsesAgentClient
from agent_orchestration.contracts import AgentRequest


class FakeCredential:
    def __init__(self):
        self.scopes: list[tuple[str, ...]] = []

    async def get_token(self, *scopes, **kwargs):
        self.scopes.append(scopes)
        return SimpleNamespace(token="test-token")


class FailingCredential:
    def __init__(self):
        self.attempts = 0

    async def get_token(self, *scopes, **kwargs):
        self.attempts += 1
        raise ClientAuthenticationError(
            "private tenant placeholder and credential diagnostic"
        )


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
    assert dict(route.calls[0].request.url.params) == {"api-version": "v1"}
    assert json.loads(route.calls[0].request.content) == {
        "input": "삼성전자 뉴스",
        "metadata": {"request_id": "req-1"},
    }


@pytest.mark.asyncio
async def test_responses_client_rejects_non_https_endpoint_before_token_acquisition():
    credential = FakeCredential()
    async with httpx.AsyncClient() as http:
        with pytest.raises(RuntimeError, match="HTTPS"):
            ResponsesAgentClient(
                "http://example.invalid/agents/News/endpoint/protocols/openai/responses",
                credential,
                http,
            )

    assert credential.scopes == []


def assert_sanitized_error(
    error: pytest.ExceptionInfo[Exception], *unsafe_values: str
) -> None:
    rendered = "".join(
        traceback.format_exception(error.type, error.value, error.value.__traceback__)
    )

    assert error.value.__cause__ is None
    for unsafe_value in unsafe_values:
        assert unsafe_value not in str(error.value)
        assert unsafe_value not in rendered


@pytest.mark.asyncio
async def test_responses_client_sanitizes_credential_acquisition_failure():
    credential = FailingCredential()
    async with httpx.AsyncClient() as http:
        client = ResponsesAgentClient(
            "https://example.invalid/agents/News/endpoint/protocols/openai/responses",
            credential,
            http,
        )
        with pytest.raises(AgentClientError) as error:
            await client.invoke(
                AgentRequest(request_id="req-1", role="News", user_query="query"),
                timeout_seconds=5,
                idempotency_key="idem-1",
            )

    assert credential.attempts == 1
    assert str(error.value) == "agent authentication failed"
    assert error.value.__context__ is None
    assert_sanitized_error(
        error,
        "private tenant placeholder",
        "credential diagnostic",
    )


@pytest.mark.asyncio
@respx.mock
async def test_responses_client_sanitizes_http_failure():
    endpoint = "https://example.invalid/private/agent-endpoint"
    route = respx.post(endpoint).mock(
        return_value=httpx.Response(401, text="private response body")
    )
    async with httpx.AsyncClient() as http:
        client = ResponsesAgentClient(endpoint, FakeCredential(), http)
        with pytest.raises(Exception) as error:
            await client.invoke(
                AgentRequest(request_id="private-request-id", role="News", user_query="private query"),
                timeout_seconds=5,
                idempotency_key="private-idempotency-key",
            )

    assert str(error.value) == "agent request failed (status=401)"
    assert_sanitized_error(
        error,
        endpoint,
        "private response body",
        "test-token",
        "private-request-id",
        "private query",
        "private-idempotency-key",
    )
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_responses_client_sanitizes_decode_failure():
    endpoint = "https://example.invalid/private/decode-endpoint"
    respx.post(endpoint).mock(
        return_value=httpx.Response(200, content=b'{"output_text":"private decode body"')
    )
    async with httpx.AsyncClient() as http:
        client = ResponsesAgentClient(endpoint, FakeCredential(), http)
        with pytest.raises(Exception) as error:
            await client.invoke(
                AgentRequest(request_id="req-1", role="News", user_query="query"),
                timeout_seconds=5,
                idempotency_key="idem-1",
            )

    assert str(error.value) == "agent response was invalid"
    assert_sanitized_error(error, endpoint, "private decode body", "test-token")


@pytest.mark.asyncio
@respx.mock
async def test_responses_client_sanitizes_extraction_failure():
    endpoint = "https://example.invalid/private/extraction-endpoint"
    respx.post(endpoint).mock(
        return_value=httpx.Response(200, json={"output_text": "private non-json output"})
    )
    async with httpx.AsyncClient() as http:
        client = ResponsesAgentClient(endpoint, FakeCredential(), http)
        with pytest.raises(Exception) as error:
            await client.invoke(
                AgentRequest(request_id="req-1", role="News", user_query="query"),
                timeout_seconds=5,
                idempotency_key="idem-1",
            )

    assert str(error.value) == "agent response was invalid"
    assert_sanitized_error(error, endpoint, "private non-json output", "test-token")


@pytest.mark.asyncio
@respx.mock
async def test_responses_client_sanitizes_validation_failure():
    endpoint = "https://example.invalid/private/validation-endpoint"
    respx.post(endpoint).mock(
        return_value=httpx.Response(
            200,
            json={
                "output_text": '{"agent":"News","status":"OK","confidence":9.9}'
            },
        )
    )
    async with httpx.AsyncClient() as http:
        client = ResponsesAgentClient(endpoint, FakeCredential(), http)
        with pytest.raises(Exception) as error:
            await client.invoke(
                AgentRequest(request_id="req-1", role="News", user_query="query"),
                timeout_seconds=5,
                idempotency_key="idem-1",
            )

    assert str(error.value) == "agent response was invalid"
    assert_sanitized_error(error, endpoint, "9.9", "test-token")


@pytest.mark.asyncio
@respx.mock
async def test_responses_client_rejects_report_for_another_role():
    endpoint = "https://example.invalid/agents/News/endpoint/protocols/openai/responses"
    respx.post(endpoint).mock(
        return_value=httpx.Response(
            200,
            json={
                "output_text": '{"agent":"Macro","status":"OK","confidence":0.9}'
            },
        )
    )
    async with httpx.AsyncClient() as http:
        client = ResponsesAgentClient(endpoint, FakeCredential(), http)
        with pytest.raises(RuntimeError, match="identity"):
            await client.invoke(
                AgentRequest(request_id="req-1", role="News", user_query="query"),
                timeout_seconds=5,
                idempotency_key="idem-1",
            )


@pytest.mark.asyncio
@respx.mock
async def test_responses_client_rejects_report_with_conflicting_request_id():
    endpoint = "https://example.invalid/agents/News/endpoint/protocols/openai/responses"
    respx.post(endpoint).mock(
        return_value=httpx.Response(
            200,
            json={
                "output_text": (
                    '{"agent":"News","request_id":"other-request","status":"OK",'
                    '"confidence":0.9}'
                )
            },
        )
    )
    async with httpx.AsyncClient() as http:
        client = ResponsesAgentClient(endpoint, FakeCredential(), http)
        with pytest.raises(RuntimeError, match="identity"):
            await client.invoke(
                AgentRequest(request_id="req-1", role="News", user_query="query"),
                timeout_seconds=5,
                idempotency_key="idem-1",
            )
