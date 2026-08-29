import os

import pytest
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential

from agent_orchestration.clients.foundry_sdk import FoundrySDKAgentClient
from agent_orchestration.config import Role, Settings
from agent_orchestration.contracts import AgentRequest
from agent_orchestration.layers import LayerController


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
    layers = LayerController()
    async with DefaultAzureCredential() as credential:
        async with AIProjectClient(
            endpoint=str(settings.foundry_project_endpoint),
            credential=credential,
        ) as project_client:
            async with project_client.get_openai_client(max_retries=0) as openai_client:
                for role in ROLES:
                    text = await FoundrySDKAgentClient(
                        openai_client,
                        settings.agent_name_for(role),
                        layers.profile_for(role),
                    ).invoke_text(
                        AgentRequest(
                            request_id=f"live-{role}",
                            role=role,
                            user_query=(
                                "연결 점검이다. 외부 도구나 주문을 실행하지 말고, "
                                "짧은 확인 응답만 반환하라."
                            ),
                        ),
                        timeout_seconds=120,
                        idempotency_key=f"live-{role}",
                    )
                    assert text.strip()
