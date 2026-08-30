from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import httpx
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient

from agent_orchestration.chatbot_bridge import (
    ChatbotMessage,
    ChatbotRegistry,
    MBGChatbotBridge,
)
from agent_orchestration.clients.foundry_sdk import FoundrySDKAgentClient
from agent_orchestration.clients.responses import ResponsesAgentClient
from agent_orchestration.config import Role, get_settings
from agent_orchestration.contracts import AgentRequest
from agent_orchestration.coordinator import AgentOrchestrator
from agent_orchestration.layers import LayerController
from agent_orchestration.planning import ClosePlanningContext
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
    runtime_context: dict | None = None,
    planning_context: ClosePlanningContext | None = None,
    chatbot_id: str | None = None,
    conversation_id: str | None = None,
    chatbot_context: dict | None = None,
) -> int:
    settings = get_settings()
    configure_logging()

    async def execute(clients):
        if chatbot_id:
            registry = ChatbotRegistry.load(
                path=settings.chatbot_registry_path,
                inline_json=settings.chatbot_registry_json,
            )
            reply = await MBGChatbotBridge(
                clients["MBGCoordinator"], registry
            ).handle(
                ChatbotMessage(
                    chatbot_id=chatbot_id,
                    message=query,
                    conversation_id=conversation_id,
                    ticker=ticker,
                    company_name=company_name,
                    context=chatbot_context or {},
                )
            )
            print(json.dumps(reply.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 0
        if coordinator_only:
            coordinator = clients["MBGCoordinator"]
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
        result = await AgentOrchestrator(clients).run(
            query,
            ticker=ticker,
            company_name=company_name,
            runtime_context=runtime_context,
            planning_context=planning_context,
        )
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

    layers = LayerController()
    async with DefaultAzureCredential() as credential:
        if settings.agent_client_backend == "foundry_sdk":
            async with AIProjectClient(
                endpoint=str(settings.foundry_project_endpoint),
                credential=credential,
            ) as project_client:
                async with project_client.get_openai_client(max_retries=0) as openai_client:
                    clients = {
                        role: FoundrySDKAgentClient(
                            openai_client,
                            settings.agent_name_for(role),
                            layers.profile_for(role),
                        )
                        for role in ROLES
                    }
                    return await execute(clients)

        async with httpx.AsyncClient() as http:
            clients = {
                role: ResponsesAgentClient(settings.endpoint_for(role), credential, http)
                for role in ROLES
            }
            return await execute(clients)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the analysis-only agent orchestrator"
    )
    parser.add_argument("query")
    parser.add_argument("--ticker")
    parser.add_argument("--company-name")
    parser.add_argument(
        "--chatbot-id",
        help="registered chatbot channel id to bridge into MBGCoordinator",
    )
    parser.add_argument("--conversation-id")
    parser.add_argument(
        "--chatbot-context-json",
        type=Path,
        help="optional channel context JSON filtered by the chatbot allowlist",
    )
    parser.add_argument(
        "--coordinator-only",
        action="store_true",
        help="send the natural-language query only to MBGCoordinator",
    )
    parser.add_argument(
        "--runtime-context-json",
        type=Path,
        help="portfolio and policy context JSON file",
    )
    parser.add_argument(
        "--planning-context-json",
        type=Path,
        help="close-of-day deterministic planning context JSON file",
    )
    args = parser.parse_args(argv)
    if args.chatbot_id and args.coordinator_only:
        parser.error("--chatbot-id and --coordinator-only cannot be used together")
    runtime_context = (
        json.loads(args.runtime_context_json.read_text(encoding="utf-8"))
        if args.runtime_context_json
        else None
    )
    planning_context = (
        ClosePlanningContext.model_validate_json(
            args.planning_context_json.read_text(encoding="utf-8")
        )
        if args.planning_context_json
        else None
    )
    chatbot_context = (
        json.loads(args.chatbot_context_json.read_text(encoding="utf-8"))
        if args.chatbot_context_json
        else None
    )
    raise SystemExit(
        asyncio.run(
            async_main(
                args.query,
                args.ticker,
                args.company_name,
                args.coordinator_only,
                runtime_context,
                planning_context,
                args.chatbot_id,
                args.conversation_id,
                chatbot_context,
            )
        )
    )


if __name__ == "__main__":
    main()
