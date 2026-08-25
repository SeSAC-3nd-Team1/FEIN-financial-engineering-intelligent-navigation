"""검증된 포트폴리오 후보를 AI 리밸런싱 제안으로 구조화한다."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.errors import ServiceError
from app.schemas.api import OperationMode


SYSTEM_PROMPT = """당신은 포트폴리오 리밸런싱 제안 모델입니다.

입력의 validated_candidates 중 지금 사용자에게 보여줄 항목을 최대 5개까지 선택하세요.
1. 후보에 없는 종목·비중·매매 방향·금액을 만들거나 변경하지 마세요.
2. priority는 1부터 중복 없이 연속되어야 합니다.
3. reason에는 해당 조정이 필요한 이유를, why_now에는 현재 시점에 제안하는 근거를 작성하세요.
4. 입력에 없는 뉴스·가격·재무 사실이나 미래 수익률을 추측하지 마세요.
5. 수익 보장이나 확정적 표현을 사용하지 말고 간결한 한국어로 작성하세요.
"""


class RebalancingCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str = Field(pattern=r"^[0-9A-Z]{6,12}$")
    stock_name: str | None = None
    current_weight: Decimal = Field(ge=0, le=100)
    target_weight: Decimal = Field(ge=0, le=100)
    weight_diff: Decimal
    action: Literal["BUY", "SELL"]
    recommended_amount: Decimal = Field(gt=0)


class RebalancingAnalysisContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_mode: OperationMode
    strategy_id: str = Field(min_length=1, max_length=30)
    total_assets: Decimal = Field(ge=0)
    cash_balance: Decimal = Field(ge=0)
    valuation_as_of: datetime | None
    validated_candidates: list[RebalancingCandidate] = Field(min_length=1)


class AIRebalancingProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str = Field(pattern=r"^[0-9A-Z]{6,12}$")
    priority: int = Field(ge=1, le=5)
    current_weight: Decimal = Field(ge=0, le=100)
    target_weight: Decimal = Field(ge=0, le=100)
    weight_diff: Decimal
    action: Literal["BUY", "SELL"]
    recommended_amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)
    why_now: str = Field(min_length=1, max_length=500)


class AIRebalancingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=500)
    proposals: list[AIRebalancingProposal] = Field(min_length=1, max_length=5)


class RebalancingAIClient(Protocol):
    async def analyze(self, context: RebalancingAnalysisContext) -> AIRebalancingResult: ...


class AzureOpenAIRebalancingClient:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.deployment = deployment
        self.api_version = api_version
        self.timeout_seconds = timeout_seconds
        self.client = client

    def _validate_configuration(self) -> None:
        if not all((self.endpoint, self.api_key, self.deployment, self.api_version)):
            raise ServiceError(
                "AI_REBALANCING_NOT_CONFIGURED",
                "리밸런싱 제안 모델이 설정되지 않았습니다.",
                503,
            )

    def _request_url(self) -> str:
        deployment = quote(self.deployment, safe="")
        return f"{self.endpoint}/openai/deployments/{deployment}/chat/completions"

    @staticmethod
    def _request_body(context: RebalancingAnalysisContext) -> dict:
        return {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(context.model_dump(mode="json"), ensure_ascii=False),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "portfolio_rebalancing",
                    "strict": True,
                    "schema": AIRebalancingResult.model_json_schema(),
                },
            },
        }

    async def analyze(self, context: RebalancingAnalysisContext) -> AIRebalancingResult:
        self._validate_configuration()
        request = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        owns_client = self.client is None
        try:
            response = await request.post(
                self._request_url(),
                params={"api-version": self.api_version},
                headers={"api-key": self.api_key, "Content-Type": "application/json"},
                json=self._request_body(context),
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ServiceError(
                "AI_REBALANCING_TIMEOUT",
                "리밸런싱 제안 생성 시간이 초과되었습니다.",
                504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = 503 if exc.response.status_code == 429 or exc.response.status_code >= 500 else 502
            raise ServiceError(
                "AI_REBALANCING_UNAVAILABLE",
                "리밸런싱 제안 모델을 사용할 수 없습니다.",
                status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise ServiceError(
                "AI_REBALANCING_UNAVAILABLE",
                "리밸런싱 제안 모델을 사용할 수 없습니다.",
                502,
            ) from exc
        finally:
            if owns_client:
                await request.aclose()

        try:
            payload = response.json()
            message = payload["choices"][0]["message"]
            content = message.get("content")
            if message.get("refusal") or not isinstance(content, str):
                raise ValueError("model did not return content")
            return AIRebalancingResult.model_validate_json(content)
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ServiceError(
                "AI_INVALID_REBALANCING_RESPONSE",
                "리밸런싱 제안 결과를 확인할 수 없습니다.",
                502,
            ) from exc
