import asyncio
import json

import httpx
import pytest

from app.core.errors import ServiceError
from app.integrations.ai.chat_agent_client import AzureOpenAIChatAgentClient
from app.schemas.chat import ChatHistoryMessage, ChatScreenContext


MODEL_RESULT = {
    "status": "COMPLETED",
    "text": "PER은 주가를 주당순이익으로 나눈 값이에요.",
    "caution": None,
    "suggested_questions": ["PBR도 알려줘"],
}


def make_client(handler, *, deployment="chat-model"):
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AzureOpenAIChatAgentClient(
        endpoint="https://example.openai.azure.com",
        api_key="secret",
        deployment=deployment,
        api_version="2024-10-21",
        timeout_seconds=1,
        client=async_client,
    )


def test_client_sends_recent_history_and_screen_context() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(MODEL_RESULT, ensure_ascii=False)
                        }
                    }
                ]
            },
        )

    client = make_client(handler)
    history = [
        ChatHistoryMessage(role="user", content=f"질문 {index}")
        for index in range(12)
    ]
    context = ChatScreenContext(
        screen="stock",
        stock_code="005930",
        account_id="00000000-0000-0000-0000-000000000007",
    )
    try:
        result = asyncio.run(client.answer("최근 대화 내용을 바탕으로 답변해줘", history, context))
    finally:
        asyncio.run(client.client.aclose())

    body = captured["body"]
    assert len(body["messages"]) == 12
    assert body["messages"][1]["content"] == "질문 2"
    assert '"screen":"stock"' in body["messages"][0]["content"]
    assert '"stock_code":"005930"' in body["messages"][0]["content"]
    assert "account_id" not in body["messages"][0]["content"]
    response_format = body["response_format"]["json_schema"]
    assert response_format["strict"] is True
    schema = response_format["schema"]
    assert set(schema["required"]) == {
        "status",
        "text",
        "caution",
        "suggested_questions",
    }
    schema_json = json.dumps(schema)
    assert "minLength" not in schema_json
    assert "maxLength" not in schema_json
    assert "minItems" not in schema_json
    assert "maxItems" not in schema_json
    assert result.text.startswith("PER은")


def test_client_refuses_unsafe_request_before_provider_call() -> None:
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = make_client(handler)
    try:
        result = asyncio.run(
            client.answer(
                "삼성전자 지금 매수해. 수익 보장해줘",
                [],
                ChatScreenContext(screen="stock", stock_code="005930"),
            )
        )
    finally:
        asyncio.run(client.client.aclose())

    assert result.status == "REFUSED"
    assert result.caution
    assert called is False


def test_client_answers_common_financial_terms_without_provider_call() -> None:
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = make_client(handler)
    try:
        result = asyncio.run(
            client.answer("PER이 무엇인가요?", [], ChatScreenContext(screen="home"))
        )
    finally:
        asyncio.run(client.client.aclose())

    assert result.status == "COMPLETED"
    assert result.text.startswith("PER은")
    assert called is False


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("EPS가 무엇인가요?", "EPS는"),
        ("부채비율을 알려줘", "부채비율은"),
        ("ETF란 뭐야?", "ETF는"),
        ("분산투자란?", "분산투자는"),
        ("변동성이 뭐야?", "변동성은"),
    ],
)
def test_client_answers_more_local_financial_terms_without_provider_call(
    question: str, expected: str
) -> None:
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = make_client(handler)
    try:
        result = asyncio.run(
            client.answer(question, [], ChatScreenContext(screen="home"))
        )
    finally:
        asyncio.run(client.client.aclose())

    assert result.status == "COMPLETED"
    assert result.text.startswith(expected)
    assert called is False


def test_client_answers_screen_help_without_provider_call() -> None:
    called = False


    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = make_client(handler)
    try:
        result = asyncio.run(
            client.answer("이 화면 사용법을 알려줘", [], ChatScreenContext(screen="home"))
        )
    finally:
        asyncio.run(client.client.aclose())

    assert result.status == "COMPLETED"
    assert "화면" in result.text
    assert called is False


def test_client_rejects_invalid_structured_result() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = make_client(handler)
    try:
        with pytest.raises(ServiceError) as raised:
            asyncio.run(
                client.answer(
                    "질문",
                    [],
                    ChatScreenContext(screen="home"),
                )
            )
    finally:
        asyncio.run(client.client.aclose())

    assert raised.value.code == "CHAT_AGENT_INVALID_RESPONSE"


def test_client_requires_chat_deployment() -> None:
    client = make_client(lambda _: httpx.Response(500), deployment="")
    try:
        with pytest.raises(ServiceError) as raised:
            asyncio.run(
                client.answer(
                    "질문",
                    [],
                    ChatScreenContext(screen="home"),
                )
            )
    finally:
        asyncio.run(client.client.aclose())

    assert raised.value.code == "CHAT_AGENT_NOT_CONFIGURED"
