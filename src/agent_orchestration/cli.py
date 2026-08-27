from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from uuid import uuid4

import httpx
from azure.identity.aio import DefaultAzureCredential

from agent_orchestration.clients.responses import ResponsesAgentClient
from agent_orchestration.config import Role, get_settings
from agent_orchestration.contracts import AgentRequest
from agent_orchestration.coordinator import AgentOrchestrator
from agent_orchestration.telemetry import configure_logging


ROLES: tuple[Role, ...] = (
    "MBGCoordinator",
    "FinancialReport",
    "News",
    "MarketResearch",
    "Macro",
    "AssetManager",
)


async def async_main(
    query: str,
    ticker: str | None = None,
    company_name: str | None = None,
    coordinator_only: bool = False,
) -> int:
    settings = get_settings()
    configure_logging()
    async with DefaultAzureCredential() as credential, httpx.AsyncClient() as http:
        if coordinator_only:
            coordinator = ResponsesAgentClient(
                settings.endpoint_for("MBGCoordinator"), credential, http
            )
            request_id = str(uuid4())
            report = await coordinator.invoke_text(
                AgentRequest(
                    request_id=request_id,
                    role="MBGCoordinator",
                    user_query=query,
                    ticker=ticker,
                    company_name=company_name,
                ),
                timeout_seconds=120,
                idempotency_key=f"{request_id}:coordinator-only",
            )
            print(report)
            return 0

        clients = {
            role: ResponsesAgentClient(settings.endpoint_for(role), credential, http)
            for role in ROLES
        }
        result = await AgentOrchestrator(clients).run(
            query,
            ticker=ticker,
            company_name=company_name,
        )
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the analysis-only agent orchestrator"
    )
    parser.add_argument("query")
    parser.add_argument("--ticker")
    parser.add_argument("--company-name")
    parser.add_argument(
        "--coordinator-only",
        action="store_true",
        help="send the natural-language query only to MBGCoordinator",
    )
    args = parser.parse_args(argv)
    raise SystemExit(
        asyncio.run(
            async_main(
                args.query,
                args.ticker,
                args.company_name,
                args.coordinator_only,
            )
        )
    )


if __name__ == "__main__":
    main()
