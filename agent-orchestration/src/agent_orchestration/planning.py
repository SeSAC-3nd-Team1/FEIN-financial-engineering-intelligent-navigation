"""Deterministic close-of-day trigger and execution handoff planning."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_orchestration.layers import GuardrailLayer


class PlanningDecision(StrEnum):
    NO_TRADE = "NO_TRADE"
    PROPOSAL_ONLY = "PROPOSAL_ONLY"
    L3_REVIEW = "L3_REVIEW"
    PAPER_ENGINE_HANDOFF = "PAPER_ENGINE_HANDOFF"


class ClosePlanningContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    backend_operation_mode: Literal["AUTO", "SEMI_AUTO"]
    execution_environment: Literal["PAPER", "LIVE"] = "PAPER"
    orchestration_mode: Literal["L4_BOUNDED_AUTO", "L3_LIVE_HITL"] = "L4_BOUNDED_AUTO"
    as_of: datetime
    market_close_received_at: datetime
    validated_candidate: bool = False
    current_weight: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    target_weight: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    current_price: Decimal = Field(gt=0)
    average_price: Decimal | None = Field(default=None, gt=0)
    peak_price: Decimal | None = Field(default=None, gt=0)
    atr20: Decimal | None = Field(default=None, gt=0)
    daily_loss_pct: Decimal = Field(default=Decimal("0"), ge=-1, le=1)
    portfolio_drawdown_pct: Decimal = Field(default=Decimal("0"), ge=-1, le=1)
    order_amount_krw: Decimal = Field(default=Decimal("0"), ge=0)
    daily_order_amount_krw: Decimal = Field(default=Decimal("0"), ge=0)
    daily_order_count: int = Field(default=0, ge=0)
    kill_switch: bool = False
    unresolved_orders: bool = False
    reconciliation_complete: bool = True
    core_data_conflict: bool = False
    market_tradable: bool = True
    is_new_symbol: bool = False
    major_event: bool = False
    thesis_broken: bool = False

    @model_validator(mode="after")
    def timezone_required(self):
        if self.as_of.tzinfo is None or self.market_close_received_at.tzinfo is None:
            raise ValueError("planning timestamps must be timezone-aware")
        return self


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: PlanningDecision
    ticker: str
    triggered: bool
    trigger_reasons: tuple[str, ...] = ()
    block_reasons: tuple[str, ...] = ()
    requires_human_approval: bool = False
    approval_ttl_minutes: int | None = None
    execution_allowed: Literal[False] = False
    handoff_target: Literal["NONE", "RISK_POLICY_ENGINE", "PAPER_ENGINE"] = "NONE"


class CloseExecutionPlanner:
    def __init__(self, guardrails: GuardrailLayer | None = None) -> None:
        self.guardrails = guardrails or GuardrailLayer()

    def evaluate(self, context: ClosePlanningContext, *, now: datetime | None = None) -> ExecutionPlan:
        evaluated_at = now or datetime.now(UTC)
        blockers: list[str] = []
        age = (evaluated_at - context.market_close_received_at.astimezone(UTC)).total_seconds()
        if age < 0 or age > 5:
            blockers.append("STALE_OR_FUTURE_CLOSE_PRICE")
        if context.kill_switch:
            blockers.append("KILL_SWITCH_ACTIVE")
        if context.unresolved_orders:
            blockers.append("UNRESOLVED_ORDERS")
        if not context.reconciliation_complete:
            blockers.append("RECONCILIATION_INCOMPLETE")
        if context.core_data_conflict:
            blockers.append("CORE_DATA_CONFLICT")
        if not context.market_tradable:
            blockers.append("MARKET_NOT_TRADABLE")
        if context.daily_loss_pct <= -Decimal(str(self.guardrails.max_daily_loss_pct)):
            blockers.append("MAX_DAILY_LOSS_REACHED")
        if context.portfolio_drawdown_pct <= -Decimal(str(self.guardrails.max_portfolio_drawdown_pct)):
            blockers.append("MAX_DRAWDOWN_REACHED")
        if context.daily_order_count >= self.guardrails.max_daily_order_count:
            blockers.append("MAX_DAILY_ORDER_COUNT")
        if context.order_amount_krw > self.guardrails.max_single_order_amount_krw:
            blockers.append("MAX_SINGLE_ORDER_AMOUNT")
        if context.daily_order_amount_krw + context.order_amount_krw > self.guardrails.max_daily_order_amount_krw:
            blockers.append("MAX_DAILY_ORDER_AMOUNT")
        if blockers:
            return ExecutionPlan(
                decision=PlanningDecision.NO_TRADE,
                ticker=context.ticker,
                triggered=False,
                block_reasons=tuple(blockers),
            )

        triggers: list[str] = []
        if context.average_price and context.current_price / context.average_price - 1 <= Decimal(str(self.guardrails.fixed_loss_review_pct)):
            triggers.append("FIXED_LOSS_REVIEW")
        if context.peak_price and context.current_price / context.peak_price - 1 <= Decimal(str(self.guardrails.trailing_drawdown_review_pct)):
            triggers.append("TRAILING_DRAWDOWN_REVIEW")
        if context.atr20 and context.average_price - context.current_price >= context.atr20 * Decimal(str(self.guardrails.atr_review_multiplier)):
            triggers.append("ATR_LOSS_REVIEW")
        if context.thesis_broken:
            triggers.append("THESIS_BREAKER")
        if context.major_event:
            triggers.append("MAJOR_EVENT")

        weight_gap = abs(context.target_weight - context.current_weight)
        if weight_gap >= Decimal(str(self.guardrails.rebalance_threshold_pct)):
            triggers.append("REBALANCE_THRESHOLD")
        if context.validated_candidate and context.target_weight > context.current_weight:
            triggers.append("VALIDATED_BUY_CANDIDATE")
        if not triggers:
            return ExecutionPlan(
                decision=PlanningDecision.NO_TRADE,
                ticker=context.ticker,
                triggered=False,
                block_reasons=("NO_TRIGGER",),
            )

        l3_reasons = {
            "FIXED_LOSS_REVIEW", "TRAILING_DRAWDOWN_REVIEW", "ATR_LOSS_REVIEW",
            "THESIS_BREAKER", "MAJOR_EVENT",
        }
        if context.is_new_symbol or context.orchestration_mode == "L3_LIVE_HITL" or l3_reasons.intersection(triggers):
            return ExecutionPlan(
                decision=PlanningDecision.L3_REVIEW,
                ticker=context.ticker,
                triggered=True,
                trigger_reasons=tuple(triggers),
                requires_human_approval=True,
                approval_ttl_minutes=self.guardrails.approval_ttl_minutes,
                handoff_target="RISK_POLICY_ENGINE",
            )
        if context.backend_operation_mode != "AUTO" or context.execution_environment != "PAPER":
            return ExecutionPlan(
                decision=PlanningDecision.PROPOSAL_ONLY,
                ticker=context.ticker,
                triggered=True,
                trigger_reasons=tuple(triggers),
                block_reasons=("AUTO_PAPER_REQUIRED",),
                handoff_target="RISK_POLICY_ENGINE",
            )
        return ExecutionPlan(
            decision=PlanningDecision.PAPER_ENGINE_HANDOFF,
            ticker=context.ticker,
            triggered=True,
            trigger_reasons=tuple(triggers),
            handoff_target="PAPER_ENGINE",
        )
