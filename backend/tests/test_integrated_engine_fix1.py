import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.trading_engine.contracts import AlgorithmSignal, EngineOrder, EngineRunRequest, EngineRunResponse
from app.trading_engine.engine_base_fix1 import IntegratedTradingEngineFix1
from app.trading_engine.engine_fix1 import IntegratedTradingEngineGateFix1


class Coordinator:
    async def propose(self, **_kwargs):
        return None


def payload(*, execute=True):
    return EngineRunRequest(
        account_id=uuid4(),
        execute=execute,
        signal=AlgorithmSignal(
            generated_at=datetime.now(UTC),
            target_weights={"005930": Decimal("0.5")},
        ),
    )


def order(index=1):
    return EngineOrder(
        stock_code=f"{index:06d}", side="BUY", quantity=Decimal("1"),
        reference_price=Decimal("100"), amount=Decimal("100"), reason="REBALANCE",
        target_weight=Decimal("0.1"), idempotency_key=f"key-{index:08d}",
    )


class ExactPlanBase:
    def __init__(self, order_count):
        self.order_count = order_count
        self.calls = []

    def plan(self, _user_id, request):
        self.calls.append("plan")
        planned_count = self.order_count
        self.order_count = 2  # a recalculation would now produce multiple orders
        return EngineRunResponse(
            account_id=request.account_id,
            generated_at=datetime.now(UTC),
            execution_mode="DRY_RUN",
            orders=[order(index) for index in range(planned_count)],
            blocked_reasons=[],
        )

    def execute_plan(self, _user_id, _request, plan):
        self.calls.append(("execute_plan", len(plan.orders)))
        if len(plan.orders) > 1:
            raise ServiceError("ATOMIC_BATCH_EXECUTION_REQUIRED", "blocked", 409)
        return plan.model_copy(update={"execution_mode": "PAPER"})


def test_multiple_orders_are_blocked_before_any_execution():
    base = ExactPlanBase(2)
    with pytest.raises(ServiceError) as error:
        asyncio.run(IntegratedTradingEngineGateFix1(base, Coordinator()).run(1, payload()))
    assert error.value.code == "ATOMIC_BATCH_EXECUTION_REQUIRED"
    assert base.calls == ["plan", ("execute_plan", 2)]


def test_first_plan_one_then_changed_state_does_not_recalculate_to_many():
    base = ExactPlanBase(1)
    result = asyncio.run(IntegratedTradingEngineGateFix1(base, Coordinator()).run(1, payload()))
    assert result.execution_mode == "PAPER"
    assert len(result.orders) == 1
    assert base.calls == ["plan", ("execute_plan", 1)]


class Repo:
    def __init__(self, mode):
        self.account = SimpleNamespace(
            id=uuid4(), status="ACTIVE", operation_mode=mode, cash_balance=Decimal("1000")
        )

    def owned_account(self, _account_id, _user_id, *, lock=False):
        return self.account

    def positions(self, _account_id):
        return []


class Market:
    def get_price(self, _symbol):
        return Decimal("100"), None, "TEST"


class Trading:
    def __init__(self):
        self.requests = []

    def execute_market_order(self, user_id, request):
        self.requests.append((user_id, request))


class Model:
    PositionInput = lambda *_args: None

    class FinConVer23Model:
        def plan(self, **_kwargs):
            return SimpleNamespace(orders=[SimpleNamespace(**order().model_dump())], blocked_reasons=[])


@pytest.mark.parametrize(
    ("mode", "expected_mode", "executions"),
    [("AUTO", "PAPER", 1), ("SEMI_AUTO", "DRY_RUN", 0)],
)
def test_only_auto_account_can_execute(mode, expected_mode, executions):
    repo = Repo(mode)
    trading = Trading()
    engine = IntegratedTradingEngineFix1(repo, Market(), trading, model_module=Model)
    request = payload(execute=True).model_copy(update={"account_id": repo.account.id})

    result = engine.run(1, request)

    assert result.execution_mode == expected_mode
    assert len(trading.requests) == executions
    if mode == "SEMI_AUTO":
        assert "PROPOSAL_ONLY_SEMI_AUTO" in result.blocked_reasons
