import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.trading_engine.contracts import AlgorithmSignal, EngineOrder, EngineRunRequest, EngineRunResponse
from app.trading_engine.engine_fix import IntegratedTradingEngineFix


class Coordinator:
    async def propose(self, **_kwargs):
        return None


class BaseEngine:
    def __init__(self, order_count):
        self.order_count = order_count
        self.calls = []
    def run(self, _user_id, request):
        self.calls.append(request.execute)
        orders = [EngineOrder(
            stock_code=f"{index:06d}", side="BUY", quantity=1,
            reference_price=100, amount=100, reason="REBALANCE",
            target_weight=Decimal("0.1"), idempotency_key=f"key-{index:08d}",
        ) for index in range(self.order_count)]
        return EngineRunResponse(
            account_id=request.account_id, generated_at=datetime.now(UTC),
            execution_mode="PAPER" if request.execute else "DRY_RUN",
            orders=orders, blocked_reasons=[],
        )


def payload(execute=True):
    return EngineRunRequest(
        account_id=uuid4(), execute=execute,
        signal=AlgorithmSignal(generated_at=datetime.now(UTC), target_weights={"005930": Decimal("0.5")}),
    )


def test_multiple_orders_are_blocked_before_any_execution():
    base = BaseEngine(2)
    with pytest.raises(ServiceError) as error:
        asyncio.run(IntegratedTradingEngineFix(base, Coordinator()).run(1, payload()))
    assert error.value.code == "ATOMIC_BATCH_EXECUTION_REQUIRED"
    assert base.calls == [False]


def test_single_order_is_planned_then_executed():
    base = BaseEngine(1)
    result = asyncio.run(IntegratedTradingEngineFix(base, Coordinator()).run(1, payload()))
    assert base.calls == [False, True]
    assert result.execution_mode == "PAPER"
