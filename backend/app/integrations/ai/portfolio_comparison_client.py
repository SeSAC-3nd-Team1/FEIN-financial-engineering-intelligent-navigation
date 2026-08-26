"""검증된 두 운용방식의 성과 지표를 화면용 AI 해설로 변환한다."""

import json
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import ServiceError


SYSTEM_PROMPT = """당신은 가상투자 성과 비교 해설 모델입니다.

입력은 Backend가 동일한 공통 관측일과 기준일로 계산한 AI 자동투자(AI_AUTO)와
사용자 투자(MY_INVESTMENT)의 검증된 지표입니다.
1. 입력에 있는 수치와 전략 정보만 사용하고 뉴스, 종목, 거래 원인 또는 미래 수익률을
   추측하지 마세요.
2. 숫자나 문장을 생성하지 말고 허용된 코드만 선택하세요. Backend가 검증된 서버 숫자로
   최종 문구를 만듭니다.
3. assessment는 입력 leader와 반드시 같아야 합니다.
4. summary_focus는 가장 유용한 비교 관점을 하나 선택하세요.
5. key_point_focuses는 중복 없이 1~3개를 선택하세요.
6. caution_code는 항상 PAST_PERFORMANCE_AND_CASH_FLOW로 반환하세요.
"""


class ComparisonAccountMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_mode: Literal["AUTO", "SEMI_AUTO"]
    strategy_id: str | None
    baseline_assets: Decimal = Field(ge=0)
    current_assets: Decimal = Field(ge=0)
    return_rate: Decimal


class PortfolioComparisonAnalysisContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: Literal["1M", "3M", "1Y", "ALL"]
    baseline_date: date
    as_of: date
    observation_count: int = Field(ge=2)
    ai_auto: ComparisonAccountMetrics
    my_investment: ComparisonAccountMetrics
    return_rate_gap: Decimal
    asset_gap: Decimal
    leader: Literal["AI_AUTO", "MY_INVESTMENT", "TIE"]


class AIPortfolioComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment: Literal["AI_AUTO", "MY_INVESTMENT", "TIE"]
    summary_focus: Literal["RETURN_GAP", "ACCOUNT_RETURNS"]
    key_point_focuses: list[
        Literal[
            "AI_AUTO_RETURN",
            "MY_INVESTMENT_RETURN",
            "RETURN_GAP",
            "OBSERVATION_COUNT",
            "ASSET_GAP",
        ]
    ] = Field(
        min_length=1,
        max_length=3,
    )
    caution_code: Literal["PAST_PERFORMANCE_AND_CASH_FLOW"]

    @model_validator(mode="after")
    def validate_unique_key_points(self) -> "AIPortfolioComparisonResult":
        if len(set(self.key_point_focuses)) != len(self.key_point_focuses):
            raise ValueError("key point focuses must be unique")
        return self


class PortfolioComparisonAIClient(Protocol):
    async def analyze(
        self,
        context: PortfolioComparisonAnalysisContext,
    ) -> AIPortfolioComparisonResult: ...


class AzureOpenAIPortfolioComparisonClient:
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
                "AI_COMPARISON_NOT_CONFIGURED",
                "투자 비교 분석 모델이 설정되지 않았습니다.",
                503,
            )

    def _request_url(self) -> str:
        deployment = quote(self.deployment, safe="")
        return f"{self.endpoint}/openai/deployments/{deployment}/chat/completions"

    @staticmethod
    def _request_body(context: PortfolioComparisonAnalysisContext) -> dict:
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
                    "name": "portfolio_comparison_analysis",
                    "strict": True,
                    "schema": AIPortfolioComparisonResult.model_json_schema(),
                },
            },
        }

    async def analyze(
        self,
        context: PortfolioComparisonAnalysisContext,
    ) -> AIPortfolioComparisonResult:
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
                "AI_COMPARISON_TIMEOUT",
                "투자 비교 분석 생성 시간이 초과되었습니다.",
                504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = 503 if exc.response.status_code == 429 or exc.response.status_code >= 500 else 502
            raise ServiceError(
                "AI_COMPARISON_UNAVAILABLE",
                "투자 비교 분석 모델을 사용할 수 없습니다.",
                status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise ServiceError(
                "AI_COMPARISON_UNAVAILABLE",
                "투자 비교 분석 모델을 사용할 수 없습니다.",
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
            return AIPortfolioComparisonResult.model_validate_json(content)
        except Exception as exc:
            raise ServiceError(
                "AI_INVALID_COMPARISON_RESPONSE",
                "투자 비교 분석 결과를 확인할 수 없습니다.",
                502,
            ) from exc
