"""Deterministic gate controlling MBGCoordinator changes to Algorithm v2.3 weights."""

from datetime import UTC, datetime
from decimal import Decimal

from app.trading_engine.contracts_fix import MBGWeightResponseFix, WeightGateConfigFix, WeightGateResultFix


class AlgorithmWeightGateFix:
    def __init__(self, config: WeightGateConfigFix = WeightGateConfigFix()) -> None:
        self.config = config

    def evaluate(self, *, baseline_weights: dict[str, Decimal], signal_generated_at: datetime,
                 agent: MBGWeightResponseFix | None, now: datetime | None = None) -> WeightGateResultFix:
        evaluated_at = now or datetime.now(UTC)
        generated = signal_generated_at
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=UTC)
        age = (evaluated_at - generated.astimezone(UTC)).total_seconds()
        reasons: list[str] = []
        approved = dict(baseline_weights)
        if age < -300 or age > self.config.max_signal_age_seconds:
            reasons.append("STALE_OR_FUTURE_ALGORITHM_SIGNAL")
            return self._result(baseline_weights, approved, False, reasons, agent, evaluated_at)
        if agent is None:
            reasons.append("COORDINATOR_UNAVAILABLE_BASELINE_USED")
            return self._result(baseline_weights, approved, False, reasons, agent, evaluated_at)
        if agent.confidence < self.config.minimum_agent_confidence:
            reasons.append("COORDINATOR_CONFIDENCE_TOO_LOW")
            return self._result(baseline_weights, approved, False, reasons, agent, evaluated_at)

        proposals = {item.stock_code: item for item in agent.proposals}
        if set(proposals) != set(baseline_weights):
            reasons.append("COORDINATOR_UNIVERSE_MISMATCH")
            return self._result(baseline_weights, approved, False, reasons, agent, evaluated_at)
        for symbol, baseline in baseline_weights.items():
            proposal = proposals[symbol]
            if proposal.baseline_weight != baseline:
                reasons.append(f"BASELINE_MISMATCH:{symbol}")
                return self._result(baseline_weights, approved, False, reasons, agent, evaluated_at)
            delta = proposal.proposed_weight - baseline
            cap = self.config.max_symbol_adjustment
            approved[symbol] = baseline + max(-cap, min(cap, delta))

        investable = Decimal("1") - self.config.cash_buffer
        total = sum(approved.values(), Decimal("0"))
        if total > investable and total > 0:
            scale = investable / total
            approved = {symbol: weight * scale for symbol, weight in approved.items()}
            reasons.append("PORTFOLIO_NORMALIZED_FOR_CASH_BUFFER")
        reasons.extend(f"COORDINATOR_RISK:{flag}" for flag in agent.risk_flags)
        reasons.append("COORDINATOR_WEIGHTS_APPLIED")
        return self._result(baseline_weights, approved, True, reasons, agent, evaluated_at)

    @staticmethod
    def _result(baseline, approved, applied, reasons, agent, evaluated_at):
        return WeightGateResultFix(
            baseline_weights=baseline, approved_weights=approved, agent_applied=applied,
            reasons=reasons, coordinator_request_id=agent.request_id if agent else None,
            evaluated_at=evaluated_at,
        )
