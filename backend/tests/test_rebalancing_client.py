"""AI 리밸런싱 client의 구조화 요청과 오류 경계를 검증한다."""

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest

from app.core.errors import ServiceError
from app.integrations.ai.rebalancing_client import (
    AzureOpenAIRebalancingClient,
    RebalancingAnalysisContext,
)


MODEL_RESULT = {
    "summary": "목표 비중과 현재 비중의 차이가 커져 점검이 필요합니다.",
    "proposals": [
        {
            "stock_code": "005930",
            "priority": 1,
            "current_weight": "20.00",
            "target_weight": "15.00",
            "weight_diff": "5.00",
            "action": "SELL",
            "recommended_amount": "50000.00",
            "reason": "목표 비중보다 높은 보유 비중을 줄이는 제안입니다.",
            "why_now": "현재 비중 차이가 5%p로 확인되어 지금 점검할 필요가 있습니다.",
        }
    ],
}


def context() -> RebalancingAnalysisContext:
    return RebalancingAnalysisContext(
        operation_mode="SEMI_AUTO",
        strategy_id="low",
        total_assets="1000000",
        cash_balance="300000",
        valuation_as_of=datetime(2026, 8, 25, tzinfo=UTC),
        validated_candidates=[
            {
                "stock_code": "005930",
                "stock_name": "삼성전자",
                "current_weight": "20.00",
                "target_weight": "15.00",
                "weight_diff": "5.00",
                "action": "SELL",
                "recommended_amount": "50000.00",
            }
        ],
    )


def make_client(handler, *, deployment="rebalancing-model"):
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AzureOpenAIRebalancingClient(
        endpoint="https://example.openai.azure.com",
        api_key="secret",
        deployment=deployment,
        api_version="2024-10-21",
        timeout_seconds=1,
        client=async_client,
    )


def test_client_sends_only_validated_candidates_as_structured_input() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(MODEL_RESULT, ensure_ascii=False)}}]},
        )

    client = make_client(handler)
    try:
        result = asyncio.run(client.analyze(context()))
    finally:
        asyncio.run(client.client.aclose())

    user_payload = json.loads(captured["body"]["messages"][1]["content"])
    assert user_payload["validated_candidates"][0]["stock_code"] == "005930"
    assert "user_id" not in user_payload
    assert "account_id" not in user_payload
    assert captured["body"]["response_format"]["json_schema"]["strict"] is True
    assert result.proposals[0].why_now.startswith("현재 비중 차이")


def test_client_rejects_invalid_structured_result() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = make_client(handler)
    try:
        with pytest.raises(ServiceError) as raised:
            asyncio.run(client.analyze(context()))
    finally:
        asyncio.run(client.client.aclose())

    assert raised.value.code == "AI_INVALID_REBALANCING_RESPONSE"


def test_client_requires_rebalancing_deployment() -> None:
    client = make_client(lambda _: httpx.Response(500), deployment="")
    try:
        with pytest.raises(ServiceError) as raised:
            asyncio.run(client.analyze(context()))
    finally:
        asyncio.run(client.client.aclose())

    assert raised.value.code == "AI_REBALANCING_NOT_CONFIGURED"
