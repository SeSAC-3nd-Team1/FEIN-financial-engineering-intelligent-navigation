from agent_orchestration.contracts import AgentReport, AgentRequest


class A2AAgentClient:
    def __init__(self, enabled: bool) -> None:
        if not enabled:
            raise RuntimeError(
                "A2A is disabled; set ALLOW_PREVIEW_A2A=true only after endpoint validation"
            )

    async def invoke(
        self,
        request: AgentRequest,
        *,
        timeout_seconds: float,
        idempotency_key: str,
    ) -> AgentReport:
        raise RuntimeError("No A2A endpoint was supplied; use the GA Responses adapter")
