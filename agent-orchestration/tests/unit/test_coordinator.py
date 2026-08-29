import asyncio

import pytest

from agent_orchestration.contracts import AgentReport, AgentRequest
from agent_orchestration.coordinator import AgentOrchestrator


class FakeClient:
    def __init__(self, role: str, started: set[str], fail: bool = False):
        self.role = role
        self.started = started
        self.fail = fail

    async def invoke(
        self,
        request: AgentRequest,
        *,
        timeout_seconds: float,
        idempotency_key: str,
    ):
        self.started.add(self.role)
        await asyncio.sleep(0)
        if self.fail:
            raise RuntimeError("unavailable")
        if self.role == "MBGCoordinator" and "계획" in request.user_query:
            return AgentReport(
                agent=self.role,
                status="OK",
                confidence=1,
                details={
                    "request_id": request.request_id,
                    "selected_roles": ["FinancialReport", "News"],
                    "tasks": {"FinancialReport": "재무 분석", "News": "뉴스 분석"},
                },
            )
        return AgentReport(agent=self.role, status="OK", confidence=0.8, summary=self.role)


@pytest.mark.asyncio
async def test_specialists_run_concurrently_and_failure_is_isolated():
    started: set[str] = set()
    clients = {
        "MBGCoordinator": FakeClient("MBGCoordinator", started),
        "FinancialReport": FakeClient("FinancialReport", started, fail=True),
        "News": FakeClient("News", started),
    }

    result = await AgentOrchestrator(clients).run(
        "삼성전자를 분석해줘", ticker="005930", company_name="삼성전자"
    )

    outcomes = {item.role: item for item in result.specialists}
    assert outcomes["FinancialReport"].error_code == "AGENT_CALL_FAILED"
    assert outcomes["News"].report is not None


@pytest.mark.asyncio
async def test_asset_manager_runs_after_parallel_research_agents():
    events: list[str] = []

    class SequencedClient(FakeClient):
        async def invoke(self, request, *, timeout_seconds, idempotency_key):
            if self.role == "MBGCoordinator" and "계획" in request.user_query:
                return AgentReport(
                    agent=self.role,
                    status="OK",
                    confidence=1,
                    details={
                        "request_id": request.request_id,
                        "selected_roles": ["FinancialReport", "News", "AssetManager"],
                        "tasks": {},
                    },
                )
            events.append(f"start:{self.role}")
            await asyncio.sleep(0)
            if self.role == "AssetManager":
                assert len(request.context["upstream_reports"]) == 2
                assert "done:FinancialReport" in events
                assert "done:News" in events
            events.append(f"done:{self.role}")
            return AgentReport(agent=self.role, status="OK", confidence=0.8)

    roles = ["MBGCoordinator", "FinancialReport", "News", "AssetManager"]
    clients = {
        role: SequencedClient(role, set())
        for role in roles
    }

    result = await AgentOrchestrator(clients).run("삼성전자를 분석해줘")

    assert [item.role for item in result.specialists] == [
        "FinancialReport", "News", "AssetManager"
    ]
