"""투자 비교 AI client의 구조화 요청과 오류 계약을 검증한다."""

import asyncio
import json
from datetime import date

import httpx
import pytest

from app.core.errors import ServiceError
from app.integrations.ai.portfolio_comparison_client import (
    AzureOpenAIPortfolioComparisonClient,
    PortfolioComparisonAnalysisContext,
)


MODEL_RESULT = {
    "headline": "AI 자동투자 수익률이 비교 기간에 앞섰습니다.",
    "summary": "공통 관측 기간 동안 5.00%p의 수익률 격차가 확인됐습니다.",
    "key_points": ["AI 자동투자 +10.00%", "내 투자 +5.00%"],
    "caution": "과거 가상투자 성과이며 미래 수익을 보장하지 않습니다.",
}


def context() -> PortfolioComparisonAnalysisContext:
    return PortfolioComparisonAnalysisContext(
        period="3M",
        baseline_date=date(2026, 8, 20),
        as_of=date(2026, 8, 25),
        observation_count=4,
        ai_auto={
            "operation_mode": "AUTO",
            "strategy_id": "low",
            "baseline_assets": "1000000",
            "current_assets": "1100000",
            "return_rate": "10.00",
        },
        my_investment={
            "operation_mode": "SEMI_AUTO",
            "strategy_id": "balanced",
            "baseline_assets": "2000000",
            "current_assets": "2100000",
            "return_rate": "5.00",
        },
        return_rate_gap="5.00",
        asset_gap="-1000000",
        leader="AI_AUTO",
    )


def make_client(handler, *, deployment="comparison-model"):
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AzureOpenAIPortfolioComparisonClient(
        endpoint="https://example.openai.azure.com",
        api_key="secret",
        deployment=deployment,
        api_version="2024-10-21",
        timeout_seconds=1,
        client=async_client,
    )


def test_client_sends_only_validated_anonymous_metrics() -> None:
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
    assert user_payload["ai_auto"]["return_rate"] == "10.00"
    assert "account_id" not in str(user_payload)
    assert "user_id" not in str(user_payload)
    assert captured["body"]["response_format"]["json_schema"]["strict"] is True
    assert result.headline.startswith("AI 자동투자")


def test_client_rejects_invalid_structured_result() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = make_client(handler)
    try:
        with pytest.raises(ServiceError) as raised:
            asyncio.run(client.analyze(context()))
    finally:
        asyncio.run(client.client.aclose())

    assert raised.value.code == "AI_INVALID_COMPARISON_RESPONSE"


def test_client_requires_comparison_deployment() -> None:
    client = make_client(lambda _: httpx.Response(500), deployment="")
    try:
        with pytest.raises(ServiceError) as raised:
            asyncio.run(client.analyze(context()))
    finally:
        asyncio.run(client.client.aclose())

    assert raised.value.code == "AI_COMPARISON_NOT_CONFIGURED"
