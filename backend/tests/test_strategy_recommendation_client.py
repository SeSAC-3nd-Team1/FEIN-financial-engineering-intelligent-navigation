import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.core.errors import ServiceError
from app.integrations.ai.strategy_recommendation_client import AzureOpenAIStrategyRecommendationClient
from app.models import InvestorProfileAssessment, Strategy


MODEL_RESULT = {
    "recommendations": [
        {"strategy_id": "value", "rank": 1, "score": 0.84, "match_level": "BEST", "reason": "균형 성향과 맞습니다.", "caution": "회복에 시간이 걸릴 수 있습니다."},
        {"strategy_id": "low", "rank": 2, "score": 0.73, "match_level": "GOOD", "reason": "안정성 선호와 맞습니다.", "caution": "상승장에서 뒤처질 수 있습니다."},
        {"strategy_id": "momentum", "rank": 3, "score": 0.51, "match_level": "CAUTION", "reason": "일부 수익 성향과 맞습니다.", "caution": "변동성이 높을 수 있습니다."},
    ]
}


def assessment() -> InvestorProfileAssessment:
    return InvestorProfileAssessment(
        id=uuid4(), user_id=7, questionnaire_version="v1", analysis_version="v1",
        profile_type="중립투자형", stability=3, return_seeking=3, horizon=4,
        tendency_line="균형을 중요하게 생각해요.", description="균형 성향입니다.",
        analysis_summary=["중장기 투자를 선호합니다."], model_version="profile-v1",
        prompt_version="v1", created_at=datetime.now(UTC),
    )


def strategies() -> list[Strategy]:
    return [
        Strategy(id="low", name="저변동성 전략", description="변동성을 낮춥니다.", risk_level="MEDIUM", rebalance_cycle="MONTHLY", rule_config={}, is_active=True),
        Strategy(id="value", name="가치 전략", description="저평가 기업을 선택합니다.", risk_level="MEDIUM", rebalance_cycle="QUARTERLY", rule_config={}, is_active=True),
        Strategy(id="momentum", name="모멘텀 전략", description="상승 흐름을 따릅니다.", risk_level="HIGH", rebalance_cycle="MONTHLY", rule_config={}, is_active=True),
    ]


def make_client(handler, *, deployment="recommendation-model"):
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AzureOpenAIStrategyRecommendationClient(
        endpoint="https://example.openai.azure.com",
        api_key="secret",
        deployment=deployment,
        api_version="2024-10-21",
        timeout_seconds=1,
        client=async_client,
    )


def test_client_sends_stored_profile_and_strategy_catalog_only() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(MODEL_RESULT, ensure_ascii=False)}}]})

    client = make_client(handler)
    try:
        result = asyncio.run(client.recommend(assessment(), strategies()))
    finally:
        asyncio.run(client.client.aclose())

    user_payload = json.loads(captured["body"]["messages"][1]["content"])
    assert user_payload["investor_profile"]["profile_type"] == "중립투자형"
    assert {item["strategy_id"] for item in user_payload["available_strategies"]} == {"low", "value", "momentum"}
    assert "answers" not in user_payload
    assert captured["body"]["response_format"]["json_schema"]["strict"] is True
    system_prompt = captured["body"]["messages"][0]["content"]
    assert "상위 최대 3개 전략" in system_prompt
    assert "모든 전략의 적합도" not in system_prompt
    assert result.recommendations[0].strategy_id == "value"


def test_client_rejects_invalid_structured_result() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = make_client(handler)
    try:
        with pytest.raises(ServiceError) as raised:
            asyncio.run(client.recommend(assessment(), strategies()))
    finally:
        asyncio.run(client.client.aclose())
    assert raised.value.code == "AI_INVALID_RECOMMENDATION"


def test_client_requires_recommendation_deployment() -> None:
    client = make_client(lambda _: httpx.Response(500), deployment="")
    try:
        with pytest.raises(ServiceError) as raised:
            asyncio.run(client.recommend(assessment(), strategies()))
    finally:
        asyncio.run(client.client.aclose())
    assert raised.value.code == "AI_RECOMMENDATION_NOT_CONFIGURED"
