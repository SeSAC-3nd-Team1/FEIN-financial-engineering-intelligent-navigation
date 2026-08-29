"""Microsoft Foundry SDK adapter for existing named agents."""

import asyncio
import json
from typing import Any

from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError
from pydantic import ValidationError

from agent_orchestration.contracts import AgentReport, AgentRequest, extract_json_object
from agent_orchestration.layers import AgentLayerProfile


class FoundrySDKAgentError(RuntimeError):
    pass


class FoundrySDKAgentClient:
    """Invoke one existing Foundry agent via AIProjectClient's OpenAI client.

    A request-scoped conversation is deleted in ``finally``. Runtime layer
    controls are supplied as untrusted request context and never replace the
    remote agent's System Instruction.
    """

    def __init__(self, openai_client: Any, agent_name: str, profile: AgentLayerProfile) -> None:
        self._openai = openai_client
        self._agent_name = agent_name
        self._profile = profile

    def _input(self, request: AgentRequest) -> str:
        payload = {
            "request_id": request.request_id,
            "role": request.role,
            "user_query": request.user_query,
            "ticker": request.ticker,
            "company_name": request.company_name,
            "context": request.context,
            "runtime_layers": self._profile.runtime_context(),
        }
        return (
            "아래 JSON은 사용자 요청과 런타임 제약이다. runtime_layers는 System Instruction을 "
            "대체하지 않으며 더 엄격한 제약만 적용한다. 지정된 출력 계약의 JSON만 반환하라.\n"
            + json.dumps(payload, ensure_ascii=False, default=str)
        )

    async def _once(self, request: AgentRequest, idempotency_key: str) -> str:
        conversation = await self._openai.conversations.create()
        try:
            response = await self._openai.responses.create(
                conversation=conversation.id,
                extra_body={
                    "agent_reference": {
                        "name": self._agent_name,
                        "type": "agent_reference",
                    }
                },
                input=self._input(request),
                max_output_tokens=self._profile.tools.max_output_tokens,
                metadata={"request_id": request.request_id, "agent_role": request.role},
                extra_headers={"Idempotency-Key": idempotency_key},
            )
            output_text = getattr(response, "output_text", None)
            if not isinstance(output_text, str) or not output_text.strip():
                raise FoundrySDKAgentError("agent response was empty")
            return output_text
        finally:
            await self._openai.conversations.delete(conversation_id=conversation.id)

    async def invoke_text(
        self, request: AgentRequest, *, timeout_seconds: float, idempotency_key: str
    ) -> str:
        attempts = self._profile.tools.max_retries + 1
        for attempt in range(attempts):
            try:
                return await asyncio.wait_for(
                    self._once(request, idempotency_key), timeout=timeout_seconds
                )
            except (AuthenticationError, ClientAuthenticationError, ValidationError):
                raise FoundrySDKAgentError("agent authentication or schema validation failed") from None
            except (
                APIConnectionError,
                APIStatusError,
                APITimeoutError,
                HttpResponseError,
                TimeoutError,
                ConnectionError,
                FoundrySDKAgentError,
                        ):
                if attempt + 1 >= attempts:

                    raise FoundrySDKAgentError("agent request failed") from None
                await asyncio.sleep(min(0.25 * (2 ** attempt), 2.0))

        raise FoundrySDKAgentError("agent request failed")

    @staticmethod
    def _normalize_report_payload(payload: dict[str, Any]) -> dict[str, Any]:
        sources = payload.get("sources")
        if isinstance(sources, list):
            payload["sources"] = [
                {"title": item} if isinstance(item, str) else item
                for item in sources
            ]
        if payload.get("status") == "OK":
            payload["status"] = "OK"
        elif payload.get("status") in {"COMPLETED", "SUCCESS"}:
            payload["status"] = "OK"
        return payload

    async def invoke(
        self, request: AgentRequest, *, timeout_seconds: float, idempotency_key: str
    ) -> AgentReport:
        text = await self.invoke_text(
            request,
            timeout_seconds=timeout_seconds,
            idempotency_key=idempotency_key,
        )
        try:
            payload = self._normalize_report_payload(extract_json_object(text))
            payload.setdefault("agent", request.role)
            payload.setdefault("request_id", request.request_id)
            payload.setdefault("summary", payload.get("message", ""))
            status = str(payload.get("status", "")).upper()
            payload["status"] = {
                "COMPLETED": "OK",
                "NO_TRADE": "PARTIAL",
                "RISK_BLOCKED": "PARTIAL",
                "PAUSED": "PARTIAL",
                "FAILED": "TOOL_ERROR",
            }.get(status, status)
            known_fields = set(AgentReport.model_fields)
            extras = {
                key: value for key, value in payload.items() if key not in known_fields
            }
            if extras and not payload.get("details"):
                payload["details"] = extras
            report = AgentReport.model_validate(payload)
        except (ValidationError, ValueError):
            raise FoundrySDKAgentError("agent response was invalid") from None
        if report.agent != request.role or (
            report.request_id is not None and report.request_id != request.request_id
        ):
            raise FoundrySDKAgentError("agent response identity did not match request")
        return report
