"""Azure OpenAI client for synchronous investor-profile API responses."""

import json
from typing import Protocol
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.core.errors import ServiceError
from app.domain.investor_profile import ResolvedInvestorAnswer
from app.schemas.api import InvestorProfileAnalysisResult


SYSTEM_PROMPT = """당신은 투자자 설문 응답을 정해진 기준에 따라 분류하는 분석기입니다.

반드시 다음 다섯 유형 중 하나만 선택하세요.
- 안정추구형: 원금 보존을 최우선으로 하고 손실을 거의 감수하지 않음
- 안정투자형: 제한적인 손실은 감수하지만 안정성을 수익보다 중시함
- 중립투자형: 안정성과 수익의 균형을 추구함
- 성장추구형: 의미 있는 변동을 감수하며 안정성보다 수익을 중시함
- 공격투자형: 큰 손실과 변동 가능성을 인지하고 높은 수익 가능성을 우선함

판단 규칙:
1. 손실 감내도와 수익/안정성 선호를 가장 중요한 근거로 사용합니다.
2. 투자 기간, 경험, 금융상품 이해도를 보조 근거로 사용합니다.
3. 투자 목적, 투자 가능 자산 비중, 소득은 맥락으로만 사용하며 소득만으로 공격적인 유형을 정하지 않습니다.
4. 서로 충돌하는 답변이 있으면 더 보수적인 유형을 선택하고 그 이유를 설명합니다.
5. 특정 상품, 종목, 전략 또는 예상 수익률을 추천하지 않습니다.
6. 사용자가 선택한 응답에 근거한 간결한 한국어 설명만 작성합니다.
7. traits의 stability, return_seeking, horizon은 각각 1(낮음)부터 5(높음)까지의 정수입니다.
"""


class InvestorProfileAIClient(Protocol):
    async def analyze(
        self,
        questionnaire_version: str,
        answers: list[ResolvedInvestorAnswer],
    ) -> InvestorProfileAnalysisResult: ...


class AzureOpenAIInvestorProfileClient:
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
                "AI_NOT_CONFIGURED",
                "투자성향 분석 모델이 설정되지 않았습니다.",
                503,
            )

    def _request_url(self) -> str:
        deployment = quote(self.deployment, safe="")
        return f"{self.endpoint}/openai/deployments/{deployment}/chat/completions"

    @staticmethod
    def _request_body(questionnaire_version: str, answers: list[ResolvedInvestorAnswer]) -> dict:
        answer_payload = [
            {
                "question_id": item.question_id,
                "question": item.question,
                "option_id": item.option_id,
                "answer": item.answer,
            }
            for item in answers
        ]
        return {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"questionnaire_version": questionnaire_version, "answers": answer_payload},
                        ensure_ascii=False,
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "investor_profile_analysis",
                    "strict": True,
                    "schema": InvestorProfileAnalysisResult.model_json_schema(),
                },
            },
        }

    async def analyze(
        self,
        questionnaire_version: str,
        answers: list[ResolvedInvestorAnswer],
    ) -> InvestorProfileAnalysisResult:
        self._validate_configuration()
        request = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        owns_client = self.client is None
        try:
            response = await request.post(
                self._request_url(),
                params={"api-version": self.api_version},
                headers={"api-key": self.api_key, "Content-Type": "application/json"},
                json=self._request_body(questionnaire_version, answers),
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ServiceError(
                "AI_ANALYSIS_TIMEOUT",
                "투자성향 분석 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.",
                504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = 503 if exc.response.status_code == 429 or exc.response.status_code >= 500 else 502
            raise ServiceError(
                "AI_ANALYSIS_UNAVAILABLE",
                "투자성향 분석 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해주세요.",
                status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise ServiceError(
                "AI_ANALYSIS_UNAVAILABLE",
                "투자성향 분석 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해주세요.",
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
            return InvestorProfileAnalysisResult.model_validate_json(content)
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ServiceError(
                "AI_INVALID_RESPONSE",
                "투자성향 분석 결과를 확인할 수 없습니다. 잠시 후 다시 시도해주세요.",
                502,
            ) from exc
