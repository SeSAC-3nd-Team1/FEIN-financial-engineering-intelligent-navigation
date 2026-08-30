import pytest

from agent_orchestration.contracts import AgentReport, AgentRequest
from agent_orchestration.coordinator import AgentOrchestrator


class IntegrationClient:
    def __init__(self, role: str):
        self.role = role

    async def invoke(
        self,
        request: AgentRequest,
        *,
        timeout_seconds: float,
        idempotency_key: str,
    ) -> AgentReport:
        if self.role == "MBGCoordinator" and "계획" in request.user_query:
            return AgentReport(
                agent=self.role,
                status="OK",
                confidence=1,
                details={
                    "request_id": request.request_id,
                    "ticker": request.ticker,
                    "company_name": request.company_name,
                    "selected_roles": [
                        "FinancialReport",
                        "News",
                        "MarketResearch",
                        "Macro",
                        "AssetManager",
                    ],
                    "tasks": {
                        "FinancialReport": "재무 분석",
                        "News": "뉴스 분석",
                        "MarketResearch": "산업 분석",
                        "Macro": "거시 분석",
                        "AssetManager": "포트폴리오 분석",
                    },
                },
            )
        return AgentReport(
            agent=self.role,
            status="OK",
            confidence=0.8,
            summary=f"{self.role} 결과",
        )


@pytest.mark.asyncio
async def test_complete_six_agent_flow_without_network():
    roles = [
        "MBGCoordinator",
        "FinancialReport",
        "News",
        "MarketResearch",
        "Macro",
        "AssetManager",
    ]
    result = await AgentOrchestrator(
        {role: IntegrationClient(role) for role in roles}
    ).run("삼성전자를 분석해줘", ticker="005930", company_name="삼성전자")

    assert len(result.specialists) == 5
    assert result.final_report.agent == "MBGCoordinator"
    assert result.trade_blocked is True
    assert "ANALYSIS_ONLY" in result.block_reasons
