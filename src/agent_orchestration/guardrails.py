from typing import Literal

from pydantic import BaseModel, Field

from agent_orchestration.universe import UniverseSnapshot


class GuardrailResult(BaseModel):
    trade_blocked: bool = True
    execution_allowed: bool = False
    block_reasons: list[str] = Field(default_factory=list)


def evaluate_guardrails(
    ticker: str | None,
    snapshot: UniverseSnapshot,
    *,
    analysis_mode: Literal["analysis_only", "paper_trading"],
) -> GuardrailResult:
    reasons: list[str] = []
    if snapshot.stale:
        reasons.append("STALE_UNIVERSE")
    if ticker is None or ticker not in snapshot.instruments:
        reasons.append("OUTSIDE_OR_UNKNOWN_UNIVERSE")
    if analysis_mode == "analysis_only":
        reasons.append("ANALYSIS_ONLY")
    return GuardrailResult(
        trade_blocked=True,
        execution_allowed=False,
        block_reasons=reasons,
    )
