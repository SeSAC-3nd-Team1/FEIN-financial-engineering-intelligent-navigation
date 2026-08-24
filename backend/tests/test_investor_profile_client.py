import asyncio
import json

import httpx
import pytest

from app.core.errors import ServiceError
from app.domain.investor_profile.questionnaire import resolve_investor_answers
from app.integrations.ai.investor_profile_client import AzureOpenAIInvestorProfileClient


ANSWERS = resolve_investor_answers("v1", [
    ("investment_experience", "1_to_3_years"),
    ("product_knowledge", "basic"),
    ("investment_horizon", "3_to_5_years"),
    ("investment_goal", "retirement"),
    ("loss_tolerance", "loss_20_percent"),
    ("risk_return_preference", "balanced"),
    ("investable_asset_ratio", "10_to_30_percent"),
    ("annual_income", "30m_to_50m"),
])

MODEL_RESULT = {
    "profile_type": "중립투자형",
    "tendency_line": "안정성과 수익의 균형을 중요하게 생각하는 투자자예요.",
    "description": "일정 수준의 변동은 감수하지만 과도한 위험은 피하는 성향입니다.",
    "traits": {"stability": 3, "return_seeking": 3, "horizon": 4},
    "analysis_summary": ["20% 수준의 손실을 감당할 수 있다고 응답했습니다."],
}


def make_client(handler, **overrides) -> AzureOpenAIInvestorProfileClient:
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AzureOpenAIInvestorProfileClient(
        endpoint=overrides.get("endpoint", "https://example.openai.azure.com"),
        api_key=overrides.get("api_key", "secret"),
        deployment=overrides.get("deployment", "profile-model"),
        api_version=overrides.get("api_version", "2024-10-21"),
        timeout_seconds=1,
        client=async_client,
    )


def test_client_sends_structured_output_request_and_parses_result() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(MODEL_RESULT, ensure_ascii=False)}}]},
        )

    client = make_client(handler)
    try:
        result = asyncio.run(client.analyze("v1", ANSWERS))
    finally:
        asyncio.run(client.client.aclose())

    request = captured["request"]
    assert str(request.url).startswith(
        "https://example.openai.azure.com/openai/deployments/profile-model/chat/completions"
    )
    assert request.url.params["api-version"] == "2024-10-21"
    assert request.headers["api-key"] == "secret"
    assert captured["body"]["response_format"]["type"] == "json_schema"
    assert captured["body"]["response_format"]["json_schema"]["strict"] is True
    assert result.profile_type == "중립투자형"


def test_client_rejects_invalid_model_result() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        invalid = {**MODEL_RESULT, "profile_type": "초고위험형"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(invalid)}}]})

    client = make_client(handler)
    try:
        with pytest.raises(ServiceError) as raised:
            asyncio.run(client.analyze("v1", ANSWERS))
    finally:
        asyncio.run(client.client.aclose())
    assert raised.value.code == "AI_INVALID_RESPONSE"
    assert raised.value.status_code == 502


def test_client_maps_timeout_to_gateway_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = make_client(handler)
    try:
        with pytest.raises(ServiceError) as raised:
            asyncio.run(client.analyze("v1", ANSWERS))
    finally:
        asyncio.run(client.client.aclose())
    assert raised.value.code == "AI_ANALYSIS_TIMEOUT"
    assert raised.value.status_code == 504


def test_client_rejects_missing_configuration_before_network_call() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    client = make_client(handler, deployment="")
    try:
        with pytest.raises(ServiceError) as raised:
            asyncio.run(client.analyze("v1", ANSWERS))
    finally:
        asyncio.run(client.client.aclose())
    assert raised.value.code == "AI_NOT_CONFIGURED"
    assert raised.value.status_code == 503
    assert calls == 0


def test_client_maps_rate_limit_to_service_unavailable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    client = make_client(handler)
    try:
        with pytest.raises(ServiceError) as raised:
            asyncio.run(client.analyze("v1", ANSWERS))
    finally:
        asyncio.run(client.client.aclose())
    assert raised.value.code == "AI_ANALYSIS_UNAVAILABLE"
    assert raised.value.status_code == 503
