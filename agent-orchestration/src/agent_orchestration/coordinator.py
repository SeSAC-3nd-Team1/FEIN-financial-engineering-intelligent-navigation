import asyncio
import json
from uuid import uuid4

from agent_orchestration.clients.base import AgentClient
from agent_orchestration.contracts import (
    AgentReport,
    AgentRequest,
    CoordinatorPlan,
    OrchestrationResult,
    SpecialistOutcome,
)
from agent_orchestration.layers import LayerController
from agent_orchestration.planning import CloseExecutionPlanner, ClosePlanningContext


class AgentOrchestrator:
    def __init__(
        self,
        clients: dict[str, AgentClient],
        timeout_seconds: float = 120,
        layer_controller: LayerController | None = None,
        execution_planner: CloseExecutionPlanner | None = None,
    ):
        self._clients = clients
        self._timeout = timeout_seconds
        self._layers = layer_controller or LayerController()
        self._execution_planner = execution_planner or CloseExecutionPlanner()

    @staticmethod
    def _coordinator_schema(*, planning: bool) -> dict:
        schema = AgentReport.model_json_schema()
        if planning:
            schema["properties"]["details"] = CoordinatorPlan.model_json_schema()
            schema["required"] = [*schema.get("required", []), "details"]
        return schema

    async def _call_specialist(
        self, role: str, request: AgentRequest
    ) -> SpecialistOutcome:
        try:
            profile = self._layers.profile_for(role)  # type: ignore[arg-type]
            report = await self._clients[role].invoke(
                request,
                timeout_seconds=min(self._timeout, profile.tools.timeout_seconds),
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
        runtime_context: dict | None = None,
        planning_context: ClosePlanningContext | None = None,
    ) -> OrchestrationResult:
        request_id = str(uuid4())
        runtime_context = runtime_context or {}
        planner_request = AgentRequest(
            request_id=request_id,
            role="MBGCoordinator",
            user_query=(
                "계획 JSON을 details에 반환하라. selected_roles는 반드시 "
                "available_agent_roles에 있는 이름만 사용하라. "
                f"사용자 요청: {query}"
            ),
            ticker=ticker,
            company_name=company_name,
            context={
                **runtime_context,
                **self._layers.request_context("MBGCoordinator"),
                "available_agent_roles": [
                    "FinancialReport",
                    "News",
                    "MarketResearch",
                    "Macro",
                    "AssetManager",
                ],
                "required_schema": self._coordinator_schema(planning=True),
            },
        )
        planning_report = await self._clients["MBGCoordinator"].invoke(
            planner_request,
            timeout_seconds=min(
                self._timeout,
                self._layers.profile_for("MBGCoordinator").tools.timeout_seconds,
            ),
            idempotency_key=f"{request_id}:plan",
        )
        plan = CoordinatorPlan.model_validate(planning_report.details)
        selected = [
            role
            for role in plan.selected_roles
            if role in self._clients and role != "MBGCoordinator"
        ]
        parallel_roles = [
            role for role in selected
            if role in {"FinancialReport", "News", "MarketResearch", "Macro"}
        ]
        outcomes = list(await asyncio.gather(
            *[
                self._call_specialist(
                    role,
                    AgentRequest(
                        request_id=request_id,
                        role=role,
                        user_query=plan.tasks.get(role, query),
                        ticker=ticker,
                        company_name=company_name,
                        context={
                            **runtime_context,
                            **self._layers.request_context(role),  # type: ignore[arg-type]
                        },
                    ),
                )
                for role in parallel_roles
            ]
        ))

        if "AssetManager" in selected and "AssetManager" in self._clients:
            asset_context = {
                **runtime_context,
                **self._layers.request_context("AssetManager"),
                "upstream_reports": [
                    item.model_dump(mode="json") for item in outcomes
                ],
            }
            outcomes.append(await self._call_specialist(
                "AssetManager",
                AgentRequest(
                    request_id=request_id,
                    role="AssetManager",
                    user_query=plan.tasks.get("AssetManager", "포트폴리오 적합성을 분석하라"),
                    ticker=ticker,
                    company_name=company_name,
                    context=asset_context,
                ),
            ))
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
            context={
                **runtime_context,
                **self._layers.request_context("MBGCoordinator"),
                "required_schema": self._coordinator_schema(planning=False),
            },
        )
        final_report = await self._clients["MBGCoordinator"].invoke(
            synthesis_request,
            timeout_seconds=min(
                self._timeout,
                self._layers.profile_for("MBGCoordinator").tools.timeout_seconds,
            ),
            idempotency_key=f"{request_id}:final",
        )
        failures = [item.role for item in outcomes if item.report is None]
        execution_plan = (
            self._execution_planner.evaluate(planning_context).model_dump(mode="json")
            if planning_context is not None
            else None
        )
        plan_blocks = execution_plan.get("block_reasons", []) if execution_plan else []
        return OrchestrationResult(
            request_id=request_id,
            plan=plan,
            specialists=outcomes,
            final_report=final_report,
            trade_blocked=True,
            block_reasons=["ANALYSIS_ONLY"]
            + [f"MISSING_{role}" for role in failures]
            + list(plan_blocks),
            execution_plan=execution_plan,
        )
