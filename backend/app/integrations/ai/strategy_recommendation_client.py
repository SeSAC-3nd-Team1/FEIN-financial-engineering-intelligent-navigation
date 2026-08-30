"""저장된 투자성향을 학습 완료 Azure OpenAI 전략 추천 모델에 전달한다."""

import json
from typing import Protocol
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.core.errors import ServiceError
from app.models import InvestorProfileAssessment, Strategy
from app.schemas.api import StrategyRecommendationAnalysisResult


SYSTEM_PROMPT = """당신은 최근 8년 금융 데이터로 학습된 투자전략 추천 모델입니다.

입력으로 제공된 투자성향과 available_strategies만 사용해 적합도가 높은 상위 최대 3개 전략을 순위화하세요.
1. 제공되지 않은 strategy_id를 만들지 마세요.
2. strategy_id와 rank는 중복될 수 없고 rank는 1부터 연속되어야 합니다.
3. score는 성향과 전략의 적합도이며 수익 확률이나 예상수익률이 아닙니다.
4. reason은 저장된 성향과 전략 특성만 근거로 간결한 한국어로 작성하세요.
5. caution에는 해당 전략의 위험이나 성향과 덜 맞는 부분을 작성하세요.
6. 미래 수익 보장, 특정 종목 매수·매도, 근거 없는 예상수익률 표현을 사용하지 마세요.
"""


class StrategyRecommendationAIClient(Protocol):
    async def recommend(
        self,
        assessment: InvestorProfileAssessment,
        strategies: list[Strategy],
    ) -> StrategyRecommendationAnalysisResult: ...


class AzureOpenAIStrategyRecommendationClient:
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
                "AI_RECOMMENDATION_NOT_CONFIGURED",
                "전략 추천 모델이 설정되지 않았습니다.",
                503,
            )

    def _request_url(self) -> str:
        deployment = quote(self.deployment, safe="")
        return f"{self.endpoint}/openai/deployments/{deployment}/chat/completions"

    @staticmethod
    def _request_body(
        assessment: InvestorProfileAssessment,
        strategies: list[Strategy],
    ) -> dict:
        payload = {
            "investor_profile": {
                "profile_type": assessment.profile_type,
                "stability": assessment.stability,
                "return_seeking": assessment.return_seeking,
                "horizon": assessment.horizon,
                "description": assessment.description,
            },
            "available_strategies": [
                {
                    "strategy_id": strategy.id,
                    "name": strategy.name,
                    "description": strategy.description,
                    "risk_level": strategy.risk_level,
                    "rebalance_cycle": strategy.rebalance_cycle,
                }
                for strategy in strategies
            ],
        }
        return {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "strategy_recommendation",
                    "strict": True,
                    "schema": StrategyRecommendationAnalysisResult.model_json_schema(),
                },
            },
        }

    async def recommend(
        self,
        assessment: InvestorProfileAssessment,
        strategies: list[Strategy],
    ) -> StrategyRecommendationAnalysisResult:
        self._validate_configuration()
        request = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        owns_client = self.client is None
        try:
            response = await request.post(
                self._request_url(),
                params={"api-version": self.api_version},
                headers={"api-key": self.api_key, "Content-Type": "application/json"},
                json=self._request_body(assessment, strategies),
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ServiceError(
                "AI_RECOMMENDATION_TIMEOUT",
                "전략 추천 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.",
                504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = 503 if exc.response.status_code == 429 or exc.response.status_code >= 500 else 502
            raise ServiceError(
                "AI_RECOMMENDATION_UNAVAILABLE",
                "전략 추천 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해주세요.",
                status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise ServiceError(
                "AI_RECOMMENDATION_UNAVAILABLE",
                "전략 추천 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해주세요.",
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
            return StrategyRecommendationAnalysisResult.model_validate_json(content)
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ServiceError(
                "AI_INVALID_RECOMMENDATION",
                "전략 추천 결과를 확인할 수 없습니다. 잠시 후 다시 시도해주세요.",
                502,
            ) from exc
