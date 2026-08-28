"""Async MBGCoordinator gate in front of the deterministic paper engine."""

from uuid import uuid4

from app.core.errors import ServiceError
from app.trading_engine.contracts import CoordinatorAdvice, EngineRunRequest, EngineRunResponse
from app.trading_engine.engine import IntegratedTradingEngine
from app.trading_engine.weight_gate_fix import AlgorithmWeightGateFix


class IntegratedTradingEngineFix:
    def __init__(self, base_engine: IntegratedTradingEngine, coordinator, gate=None) -> None:
        self.base_engine = base_engine
        self.coordinator = coordinator
        self.gate = gate or AlgorithmWeightGateFix()

    async def run(self, user_id: int, request: EngineRunRequest) -> EngineRunResponse:
        request_id = f"mbg-weight-{uuid4()}"
        try:
            agent = await self.coordinator.propose(
                request_id=request_id,
                generated_at=request.signal.generated_at.isoformat(),
                baseline_weights={key: str(value) for key, value in request.signal.target_weights.items()},
                market_context=request.coordinator_advice.model_dump(mode="json") if request.coordinator_advice else {},
            )
        except Exception:
            agent = None
        gated = self.gate.evaluate(
            baseline_weights=request.signal.target_weights,
            signal_generated_at=request.signal.generated_at,
            agent=agent,
        )
        if "STALE_OR_FUTURE_ALGORITHM_SIGNAL" in gated.reasons:
            raise ServiceError("STALE_ALGORITHM_SIGNAL", "오래되었거나 미래 시점인 알고리즘 신호입니다.", 409)
        advice = CoordinatorAdvice(
            request_id=gated.coordinator_request_id or request_id,
            confidence=agent.confidence if agent else 0,
            blocked_symbols=[],
            risk_flags=gated.reasons,
            summary=agent.summary if agent else "MBGCoordinator 미적용; Algorithm 기준 비중 사용",
        )
        fixed = request.model_copy(update={
            "signal": request.signal.model_copy(update={"target_weights": gated.approved_weights}),
            "coordinator_advice": advice,
            "cash_buffer": self.gate.config.cash_buffer,
            "execute": False,
        })
        plan = self.base_engine.run(user_id, fixed)
        if not request.execute:
            return plan
        if len(plan.orders) > 1:
            raise ServiceError(
                "ATOMIC_BATCH_EXECUTION_REQUIRED",
                "여러 리밸런싱 주문은 원자적 배치 체결 구현 전까지 실행할 수 없습니다.",
                409,
            )
        return self.base_engine.run(user_id, fixed.model_copy(update={"execute": True}))
