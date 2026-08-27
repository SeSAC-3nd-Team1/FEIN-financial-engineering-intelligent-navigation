from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_orchestration.universe import (
    ASSET_TYPE_POLICY,
    AssetType,
    UniverseSnapshot,
    UniverseTarget,
    canonicalize_ticker,
    coerce_asset_type,
    is_valid_identifier,
)


class GuardrailResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    trade_blocked: Literal[True] = True
    execution_allowed: Literal[False] = False
    block_reasons: list[str] = Field(default_factory=list)


def evaluate_guardrails(
    ticker: str | UniverseTarget | None,
    snapshot: UniverseSnapshot | None,
    *,
    analysis_mode: str,
    asset_type: AssetType | str | None = None,
) -> GuardrailResult:
    reasons: list[str] = []

    if analysis_mode == "analysis_only":
        reasons.append("ANALYSIS_ONLY")
    elif analysis_mode == "paper_trading":
        reasons.append("PAPER_TRADING_NO_EXECUTION")
    else:
        reasons.append("INVALID_ANALYSIS_MODE")

    if snapshot is None:
        reasons.append("UNIVERSE_UNAVAILABLE")
        return GuardrailResult(block_reasons=reasons)

    if snapshot.stale:
        reasons.append("STALE_UNIVERSE")

    target_ticker = ticker.ticker if isinstance(ticker, UniverseTarget) else ticker
    target_asset_type = ticker.asset_type if isinstance(ticker, UniverseTarget) else None
    requested_asset_type = (
        coerce_asset_type(asset_type)
        if asset_type is not None
        else target_asset_type
    )
    if target_ticker is None or not isinstance(target_ticker, str) or not target_ticker.strip():
        reasons.append("OUTSIDE_OR_UNKNOWN_UNIVERSE")
        if requested_asset_type is AssetType.UNKNOWN:
            reasons.append("UNKNOWN_ASSET_TYPE")
        return GuardrailResult(block_reasons=reasons)

    try:
        canonical_ticker = canonicalize_ticker(target_ticker, requested_asset_type)
    except ValueError:
        reasons.append("INVALID_IDENTIFIER")
        return GuardrailResult(block_reasons=reasons)

    configured_asset_type = snapshot.instruments.get(canonical_ticker)
    if configured_asset_type is None:
        reasons.append("OUTSIDE_OR_UNKNOWN_UNIVERSE")
        if requested_asset_type is AssetType.UNKNOWN:
            reasons.append("UNKNOWN_ASSET_TYPE")
        return GuardrailResult(block_reasons=reasons)

    effective_asset_type = requested_asset_type or configured_asset_type
    if requested_asset_type is not None and requested_asset_type != configured_asset_type:
        reasons.append("ASSET_TYPE_MISMATCH")

    if effective_asset_type is AssetType.UNKNOWN:
        reasons.append("UNKNOWN_ASSET_TYPE")
    elif not ASSET_TYPE_POLICY[effective_asset_type]:
        reasons.append("UNSUPPORTED_ASSET_TYPE")
    elif not is_valid_identifier(canonical_ticker, effective_asset_type):
        reasons.append("INVALID_IDENTIFIER")

    return GuardrailResult(block_reasons=reasons)
