"""Entra-authenticated Responses adapter for the MBGCoordinator endpoint."""

import json
from typing import Protocol

import httpx

from app.trading_engine.contracts_fix1 import MBGWeightResponseFix


DEFAULT_MBG_COORDINATOR_ENDPOINT = (
    "https://fein-agent.services.ai.azure.com/api/projects/proj-default/agents/"
    "MBGCoordinator/endpoint/protocols/openai/responses"
)


class AsyncCredentialFix(Protocol):
    async def get_token(self, *scopes: str): ...


class MBGCoordinatorAdapterFix1:
    def __init__(self, credential: AsyncCredentialFix, *, endpoint: str = DEFAULT_MBG_COORDINATOR_ENDPOINT,
                 http: httpx.AsyncClient | None = None, timeout_seconds: float = 30) -> None:
        url = httpx.URL(endpoint)
        if url.scheme != "https":
            raise ValueError("MBGCoordinator endpoint must use HTTPS")
        self.endpoint = url.copy_set_param("api-version", "v1")
        self.credential = credential
        self.http = http
        self.timeout_seconds = timeout_seconds

    async def propose(self, *, request_id: str, generated_at: str,
                      baseline_weights: dict[str, str], market_context: dict) -> MBGWeightResponseFix:
        token = await self.credential.get_token("https://ai.azure.com/.default")
        prompt = {
            "task": "Algorithm v2.3 목표 주식비중 수정안 생성",
            "rules": [
                "baseline_weights에 존재하는 종목만 제안한다.",
                "모든 종목에 대해 baseline_weight와 proposed_weight를 0~1로 반환한다.",
                "수익을 보장하지 말고 제공된 market_context만 근거로 사용한다.",
                "반드시 JSON 객체 하나만 반환한다.",
            ],
            "response_schema": MBGWeightResponseFix.model_json_schema(),
            "request_id": request_id,
            "generated_at": generated_at,
            "baseline_weights": baseline_weights,
            "market_context": market_context,
        }
        client = self.http or httpx.AsyncClient(timeout=self.timeout_seconds)
        owns_client = self.http is None
        try:
            response = await client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {token.token}", "Content-Type": "application/json",
                         "Idempotency-Key": request_id},
                json={"input": json.dumps(prompt, ensure_ascii=False), "metadata": {"request_id": request_id}},
            )
            response.raise_for_status()
            payload = response.json()
            text = payload.get("output_text") if isinstance(payload, dict) else None
            if not isinstance(text, str):
                text = "".join(
                    content.get("text", "")
                    for item in payload.get("output", []) if isinstance(item, dict)
                    for content in item.get("content", [])
                    if isinstance(content, dict) and content.get("type") == "output_text"
                )
            result = MBGWeightResponseFix.model_validate_json(text)
            if result.request_id != request_id:
                raise ValueError("MBGCoordinator request_id mismatch")
            return result
        finally:
            if owns_client:
                await client.aclose()
