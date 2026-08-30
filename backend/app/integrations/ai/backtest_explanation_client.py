"""Azure OpenAI client for explaining already-calculated backtest metrics."""

from datetime import UTC, datetime
import json
from typing import Protocol
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.core.errors import ServiceError
from app.schemas.api import (
    BacktestAiGeneratedText,
    BacktestAiExplanationResponse,
    BacktestAiInput,
)


SYSTEM_PROMPT = """당신은 FE!N의 금융 설명 도우미 물방개입니다.

제공되는 모든 숫자는 실제 과거 데이터로 백테스트 엔진이 계산한 확정값입니다.
숫자를 변경하거나 재계산하지 말고, 제공되지 않은 사실을 추가하지 마세요.
투자 초보자가 이해할 수 있도록 수익성과 위험을 함께 쉽게 설명하세요.
미래 수익을 예측하거나 보장하지 말고, 매수 또는 매도를 권유하지 마세요.

benchmarkDifference는 Backend가 미리 계산한 전략 누적수익률과 benchmark 누적수익률의
확정 차이(%p)입니다. 이를 다시 계산하지 말고 그대로 사용하세요.
응답은 반드시 아래 JSON schema만 사용하세요.
- headline: 한 문장. benchmarkName 대비 성과와 benchmarkDifference를 설명하세요.
- overview: 1~2문장. cumulativeReturn과 cagr의 의미를 쉽게 설명하세요.
- caution: 1~2문장. mdd, volatility, sharpe의 위험 의미를 설명하세요.
각 필드는 짧은 한국어 문장으로 작성하고, 입력 숫자의 값을 반올림하거나 바꾸지 마세요.
"""


class BacktestExplanationAIClient(Protocol):
    async def explain(self, context: BacktestAiInput) -> BacktestAiExplanationResponse: ...


class AzureOpenAIBacktestExplanationClient:
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
            raise ServiceError("AI_BACKTEST_EXPLANATION_NOT_CONFIGURED", "백테스트 설명 모델이 설정되지 않았습니다.", 503)

    def _request_url(self) -> str:
        return f"{self.endpoint}/openai/deployments/{quote(self.deployment, safe='')}/chat/completions"

    @staticmethod
    def _request_body(context: BacktestAiInput) -> dict:
        return {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context.model_dump(mode="json"), ensure_ascii=False)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "backtest_explanation",
                    "strict": True,
                    "schema": BacktestAiGeneratedText.model_json_schema(),
                },
            },
        }

    async def explain(self, context: BacktestAiInput) -> BacktestAiExplanationResponse:
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
            raise ServiceError("AI_BACKTEST_EXPLANATION_TIMEOUT", "백테스트 설명 시간이 초과되었습니다.", 504) from exc
        except httpx.HTTPStatusError as exc:
            status_code = 503 if exc.response.status_code == 429 or exc.response.status_code >= 500 else 502
            raise ServiceError("AI_BACKTEST_EXPLANATION_UNAVAILABLE", "백테스트 설명 서비스를 사용할 수 없습니다.", status_code) from exc
        except httpx.RequestError as exc:
            raise ServiceError("AI_BACKTEST_EXPLANATION_UNAVAILABLE", "백테스트 설명 서비스를 사용할 수 없습니다.", 502) from exc
        finally:
            if owns_client:
                await request.aclose()

        try:
            payload = response.json()
            message = payload["choices"][0]["message"]
            content = message.get("content")
            if message.get("refusal") or not isinstance(content, str):
                raise ValueError("model did not return content")
            generated = BacktestAiGeneratedText.model_validate_json(content)
            return BacktestAiExplanationResponse(
                **generated.model_dump(),
                generated_at=datetime.now(UTC),
            )
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ServiceError("AI_INVALID_BACKTEST_EXPLANATION", "백테스트 설명 결과를 확인할 수 없습니다.", 502) from exc
