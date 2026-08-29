from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.trading_engine.contracts import AlgorithmSignal, CoordinatorAdvice, EngineRunRequest
from app.trading_engine.engine import IntegratedTradingEngine


class Repo:
    def __init__(self, account, positions):
        self.account, self._positions = account, positions
    def owned_account(self, *_args): return self.account
    def positions(self, *_args): return self._positions


class Market:
    def __init__(self, prices): self.prices = prices
    def get_price(self, symbol): return Decimal(self.prices[symbol]), None, "TEST"


class Trading:
    def __init__(self): self.requests = []
    def execute_market_order(self, user_id, request): self.requests.append((user_id, request))


def request(account_id, *, execute=False, advice=None):
    return EngineRunRequest(
        account_id=account_id, execute=execute, min_order_amount=Decimal("1"),
        signal=AlgorithmSignal(
            generated_at=datetime(2026, 8, 28, tzinfo=UTC),
            target_weights={"005930": Decimal("0.40"), "000660": Decimal("0.40")},
            stop_prices={"005930": Decimal("90")},
        ), coordinator_advice=advice,
    )


def test_stop_loss_precedes_rebalancing_and_is_not_vetoed():
    account_id = uuid4()
    account = SimpleNamespace(id=account_id, status="ACTIVE", cash_balance=Decimal("800"))
    positions = [SimpleNamespace(stock_code="005930", quantity=Decimal("2"), average_price=Decimal("120"))]
    advice = CoordinatorAdvice(request_id="mbg-1", confidence=Decimal("0.8"), blocked_symbols=["005930"])
    engine = IntegratedTradingEngine(Repo(account, positions), Market({"005930": "80", "000660": "100"}), Trading())

    result = engine.run(1, request(account_id, advice=advice))

    stop = next(order for order in result.orders if order.stock_code == "005930")
    assert stop.reason == "STOP_LOSS"
    assert stop.side == "SELL"
    assert stop.quantity == 2
    assert result.execution_mode == "DRY_RUN"


def test_execute_sells_before_buys_and_is_idempotent():
    account_id = uuid4()
    account = SimpleNamespace(id=account_id, status="ACTIVE", cash_balance=Decimal("100"))
    positions = [SimpleNamespace(stock_code="005930", quantity=Decimal("5"), average_price=Decimal("100"))]
    trading = Trading()
    engine = IntegratedTradingEngine(Repo(account, positions), Market({"005930": "100", "000660": "100"}), trading)

    first = engine.run(1, request(account_id, execute=True))
    second = engine.run(1, request(account_id, execute=True))

    assert first.execution_mode == "PAPER"
    assert [item[1].side for item in trading.requests[:2]] == ["SELL", "BUY"]
    assert [item.idempotency_key for item in first.orders] == [item.idempotency_key for item in second.orders]


def test_turnover_budget_scales_rebalance():
    account_id = uuid4()
    account = SimpleNamespace(id=account_id, status="ACTIVE", cash_balance=Decimal("1000"))
    engine = IntegratedTradingEngine(Repo(account, []), Market({"005930": "100", "000660": "100"}), Trading())

    result = engine.run(1, request(account_id))

    assert sum(order.amount for order in result.orders) <= Decimal("300.01")
