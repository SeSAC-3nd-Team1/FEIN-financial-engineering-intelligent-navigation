import asyncio
import json
from uuid import uuid4

from agent_orchestration.clients.base import AgentClient
from agent_orchestration.contracts import (
    AgentRequest,
    CoordinatorPlan,
    OrchestrationResult,
    SpecialistOutcome,
)


class AgentOrchestrator:
    def __init__(self, clients: dict[str, AgentClient], timeout_seconds: float = 120):
        self._clients = clients
        self._timeout = timeout_seconds

    async def _call_specialist(
        self, role: str, request: AgentRequest
    ) -> SpecialistOutcome:
        try:
            report = await self._clients[role].invoke(
                request,
                timeout_seconds=self._timeout,
                idempotency_key=f"{request.request_id}:{role}",
            )
            return SpecialistOutcome(role=role, report=report)
        except Exception as exc:
            return SpecialistOutcome(
                role=role,
                error_code="AGENT_CALL_FAILED",
                error_message=type(exc).__name__,
            )

    async def run(
        self,
        query: str,
        *,
        ticker: str | None = None,
        company_name: str | None = None,
    ) -> OrchestrationResult:
        request_id = str(uuid4())
        planner_request = AgentRequest(
            request_id=request_id,
            role="MBGCoordinator",
            user_query=f"계획 JSON을 details에 반환하라. 사용자 요청: {query}",
            ticker=ticker,
            company_name=company_name,
        )
        planning_report = await self._clients["MBGCoordinator"].invoke(
            planner_request,
            timeout_seconds=self._timeout,
            idempotency_key=f"{request_id}:plan",
        )
        plan = CoordinatorPlan.model_validate(planning_report.details)
        selected = [
            role
            for role in plan.selected_roles
            if role in self._clients and role != "MBGCoordinator"
        ]
        outcomes = await asyncio.gather(
            *[
                self._call_specialist(
                    role,
                    AgentRequest(
                        request_id=request_id,
                        role=role,
                        user_query=plan.tasks.get(role, query),
                        ticker=ticker,
                        company_name=company_name,
                    ),
                )
                for role in selected
            ]
        )
        synthesis_request = AgentRequest(
            request_id=request_id,
            role="MBGCoordinator",
            user_query=(
                "전문 보고서를 검증·종합해 최종 JSON 보고서를 반환하라.\n"
                + json.dumps(
                    [item.model_dump(mode="json") for item in outcomes],
                    ensure_ascii=False,
                )
            ),
            ticker=ticker,
            company_name=company_name,
        )
        final_report = await self._clients["MBGCoordinator"].invoke(
            synthesis_request,
            timeout_seconds=self._timeout,
            idempotency_key=f"{request_id}:final",
        )
        failures = [item.role for item in outcomes if item.report is None]
        return OrchestrationResult(
            request_id=request_id,
            plan=plan,
            specialists=outcomes,
            final_report=final_report,
            trade_blocked=True,
            block_reasons=["ANALYSIS_ONLY"]
            + [f"MISSING_{role}" for role in failures],
        )
