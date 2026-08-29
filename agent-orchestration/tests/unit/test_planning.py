from datetime import UTC, datetime
from decimal import Decimal

from agent_orchestration.planning import (
    CloseExecutionPlanner,
    ClosePlanningContext,
    PlanningDecision,
)


NOW = datetime(2026, 8, 29, 6, 30, tzinfo=UTC)


def context(**updates):
    payload = {
        "ticker": "005930",
        "backend_operation_mode": "AUTO",
        "execution_environment": "PAPER",
        "as_of": NOW,
        "market_close_received_at": NOW,
        "validated_candidate": True,
        "current_weight": Decimal("0.02"),
        "target_weight": Decimal("0.08"),
        "current_price": Decimal("70000"),
        "order_amount_krw": Decimal("1000000"),
    }
    payload.update(updates)
    return ClosePlanningContext(**payload)


def test_auto_paper_candidate_is_handed_only_to_paper_engine():
    result = CloseExecutionPlanner().evaluate(context(), now=NOW)

    assert result.decision is PlanningDecision.PAPER_ENGINE_HANDOFF
    assert result.handoff_target == "PAPER_ENGINE"
    assert result.execution_allowed is False


def test_semi_auto_is_proposal_only():
    result = CloseExecutionPlanner().evaluate(
        context(backend_operation_mode="SEMI_AUTO"), now=NOW
    )

    assert result.decision is PlanningDecision.PROPOSAL_ONLY
    assert "AUTO_PAPER_REQUIRED" in result.block_reasons


def test_stop_loss_trigger_requires_l3_approval():
    result = CloseExecutionPlanner().evaluate(
        context(average_price=Decimal("100000"), current_price=Decimal("80000")),
        now=NOW,
    )

    assert result.decision is PlanningDecision.L3_REVIEW
    assert result.requires_human_approval is True
    assert result.approval_ttl_minutes == 5


def test_stale_close_or_kill_switch_fails_closed():
    stale = NOW.replace(second=10)
    result = CloseExecutionPlanner().evaluate(
        context(kill_switch=True), now=stale
    )

    assert result.decision is PlanningDecision.NO_TRADE
    assert set(result.block_reasons) >= {"STALE_OR_FUTURE_CLOSE_PRICE", "KILL_SWITCH_ACTIVE"}
