from typing import Protocol

from agent_orchestration.contracts import AgentReport, AgentRequest


class AgentClient(Protocol):
    async def invoke(
        self,
        request: AgentRequest,
        *,
        timeout_seconds: float,
        idempotency_key: str,
    ) -> AgentReport:
        ...
