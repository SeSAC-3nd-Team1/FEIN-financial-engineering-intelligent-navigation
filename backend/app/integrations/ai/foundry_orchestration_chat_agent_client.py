"""Backend adapter for the in-process FE!N chatbot -> MBGCoordinator path."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from azure.identity.aio import DefaultAzureCredential
from openai import AsyncOpenAI

from agent_orchestration.chatbot_bridge import (
    ChatbotMessage,
    ChatbotRegistry,
    MBGChatbotBridge,
    ChatbotConfigurationError,
    ChatbotDisabledError,
    ChatbotNotRegisteredError,
)
from agent_orchestration.clients.foundry_sdk import FoundrySDKAgentClient
from agent_orchestration.config import Role
from agent_orchestration.contracts import AgentRequest, extract_json_object
from agent_orchestration.coordinator import AgentOrchestrator
from agent_orchestration.layers import LayerController
from app.core.errors import ServiceError
from app.schemas.chat import ChatAgentResult, ChatHistoryMessage, ChatScreenContext


logger = logging.getLogger(__name__)


ROLES: tuple[Role, ...] = (
    "MBGCoordinator",
    "FinancialReport",
    "News",
    "MarketResearch",
    "Macro",
    "AssetManager",
)


class _CoordinatorBridgeClient:
    def __init__(self, orchestrator: AgentOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def invoke_text(
        self, request: AgentRequest, *, timeout_seconds: float, idempotency_key: str
    ) -> str:
        del timeout_seconds, idempotency_key
        result = await self._orchestrator.run(
            request.user_query,
            ticker=request.ticker,
            company_name=request.company_name,
            runtime_context=request.context,
        )
        return result.final_report.model_dump_json()


class FoundryOrchestrationChatAgentClient:
    """Use Managed Identity/CLI credentials without invoking the orchestration CLI."""

    def __init__(
        self,
        *,
        project_endpoint: str,
        agent_names: dict[Role, str],
        registry_json: str,
        chatbot_id: str,
        timeout_seconds: float,
    ) -> None:
        self.project_endpoint = project_endpoint
        self.agent_names = agent_names
        self.registry_json = registry_json
        self.chatbot_id = chatbot_id
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _public_context(
        context: ChatScreenContext,
        personal_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        public_context = context.model_dump(
            include={"screen", "stock_code", "strategy_id"}, exclude_none=True
        )
        if personal_context:
            public_context["verified_personal_summary"] = personal_context
        return public_context

    @staticmethod
    def _result(output: str) -> ChatAgentResult:
        text = output.strip()
        caution = "답변은 금융 교육 및 정보 제공 목적이며, 최종 투자 결정은 사용자에게 있습니다."
        suggested = ["관련 금융 지표를 더 알려줘", "이 화면에서 무엇을 볼 수 있나요?"]
        try:
            payload = extract_json_object(text)
            if isinstance(payload, dict):
                text = str(payload.get("summary") or payload.get("message") or text)
                caution = str(payload.get("caution") or caution)
                suggested = [str(item) for item in payload.get("suggested_questions", suggested)][:3]
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        return ChatAgentResult(
            status="COMPLETED",
            text=text[:2000],
            caution=caution[:500],
            suggested_questions=suggested,
        )

    async def answer(
        self,
        message: str,
        history: list[ChatHistoryMessage],
        context: ChatScreenContext,
        *,
        session: Any | None = None,
        user_id: int | None = None,
        account_id: Any | None = None,
    ) -> ChatAgentResult:
        del history  # Bridge owns the coordinator conversation boundary.
        if not self.registry_json.strip():
            raise ServiceError("CHAT_AGENT_NOT_CONFIGURED", "물방개 AI가 설정되지 않았습니다.", 503)
        try:
            registry = ChatbotRegistry.from_json(self.registry_json)
        except ChatbotConfigurationError as exc:
            raise ServiceError("CHAT_AGENT_NOT_CONFIGURED", "물방개 AI가 설정되지 않았습니다.", 503) from exc

        personal_context: dict[str, Any] | None = None
        if session is not None and user_id is not None:
            from app.services.chat_tools import (
                get_my_account_summary,
                get_my_portfolio_summary,
            )

            personal_context = {
                "account": get_my_account_summary(
                    session, user_id, account_id=account_id
                ),
                "portfolio": get_my_portfolio_summary(
                    session, user_id, account_id=account_id
                ),
            }

        credential = DefaultAzureCredential()
        openai_client: AsyncOpenAI | None = None
        try:
            token = await credential.get_token("https://ai.azure.com/.default")
            openai_client = AsyncOpenAI(
                api_key=token.token,
                base_url=f"{self.project_endpoint.rstrip('/')}/openai/v1",
                max_retries=0,
            )
            layers = LayerController()
            clients = {
                role: FoundrySDKAgentClient(
                    openai_client,
                    self.agent_names[role],
                    layers.profile_for(role),
                )
                for role in ROLES
            }
            reply = await MBGChatbotBridge(
                _CoordinatorBridgeClient(AgentOrchestrator(clients)), registry
            ).handle(
                ChatbotMessage(
                    chatbot_id=self.chatbot_id,
                    message=message,
                    request_id=str(uuid4()),
                    context=self._public_context(context, personal_context),
                )
            )
            if reply.execution_allowed is not False:
                raise ServiceError("CHAT_AGENT_POLICY_BLOCKED", "허용되지 않은 실행 요청입니다.", 502)
            return self._result(reply.output_text)
        except (ChatbotNotRegisteredError, ChatbotDisabledError) as exc:
            raise ServiceError("CHAT_AGENT_CHANNEL_UNAVAILABLE", "물방개 채널을 사용할 수 없습니다.", 503) from exc
        except ServiceError:
            raise
        except Exception as exc:
            logger.exception(
                "Foundry chatbot request failed type=%s chatbot_id=%s",
                type(exc).__name__,
                self.chatbot_id,
            )
            raise ServiceError("CHAT_AGENT_UNAVAILABLE", "물방개 AI를 사용할 수 없습니다. 잠시 후 다시 시도해주세요.", 503) from exc
        finally:
            if openai_client is not None:
                await openai_client.close()
            await credential.close()
