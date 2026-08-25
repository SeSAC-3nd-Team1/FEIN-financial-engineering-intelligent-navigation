"""포트폴리오 분석용 판단 이력 모델의 감사 제약을 검증한다."""

from db.models import RebalancingDecision


def test_rebalancing_decision_preserves_server_proposal_and_idempotency() -> None:
    columns = set(RebalancingDecision.__table__.columns.keys())
    constraints = {
        constraint.name for constraint in RebalancingDecision.__table__.constraints if constraint.name
    }
    foreign_keys = {
        foreign_key.target_fullname for foreign_key in RebalancingDecision.__table__.foreign_keys
    }

    assert {
        "current_weight", "target_weight", "weight_diff", "recommended_amount",
        "decision", "baseline_snapshot_date", "baseline_total_assets", "idempotency_key",
    } <= columns
    assert {
        "uq_rebalancing_decisions_account_idempotency",
        "ck_rebalancing_decisions_action_values",
        "ck_rebalancing_decisions_decision_values",
    } <= constraints
    assert foreign_keys == {"virtual_accounts.id", "strategies.id"}
