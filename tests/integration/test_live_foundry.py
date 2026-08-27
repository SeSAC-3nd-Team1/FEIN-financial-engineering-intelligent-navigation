import os

import httpx
import pytest
from azure.identity.aio import DefaultAzureCredential

from agent_orchestration.clients.responses import ResponsesAgentClient
from agent_orchestration.config import Role, Settings
from agent_orchestration.contracts import AgentRequest


ROLES: tuple[Role, ...] = (
    "MBGCoordinator",
    "FinancialReport",
    "News",
    "MarketResearch",
    "Macro",
    "AssetManager",
)


@pytest.mark.live
@pytest.mark.asyncio
async def test_all_configured_foundry_agents_are_reachable():
    if os.getenv("RUN_LIVE_FOUNDRY_TESTS", "false").lower() != "true":
        pytest.skip("set RUN_LIVE_FOUNDRY_TESTS=true to run live Foundry tests")

    settings = Settings()
    async with DefaultAzureCredential() as credential, httpx.AsyncClient() as http:
        for role in ROLES:
            report = await ResponsesAgentClient(
                settings.endpoint_for(role), credential, http
            ).invoke(
                AgentRequest(
                    request_id=f"live-{role}",
                    role=role,
                    user_query=(
                        "연결 점검이다. 외부 도구나 주문을 실행하지 말고, "
                        "status와 summary를 포함한 JSON만 반환하라."
                    ),
                ),
                timeout_seconds=120,
                idempotency_key=f"live-{role}",
            )
            assert report.agent == role
