"""가상 체결의 금액·수량·원장 원자성을 검증한다."""

from contextlib import nullcontext
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.models import CashLedger, Execution, Position, VirtualAccount
from app.schemas.api import OrderCreateRequest
from app.services.trading import TradingService


class FakeSession:
    def __init__(self) -> None:
        self.added = []

    def begin(self):
        return nullcontext()

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for value in self.added:
            if value.__class__.__name__ == "Order" and value.id is None:
                value.id = uuid4()

    def commit(self):
        pass

    def rollback(self):
        pass


class FixedMarket:
    def __init__(self, price: str) -> None:
        self.price = Decimal(price)

    def get_price(self, _):
        return self.price, None, "TEST"


class FakeRepo:
    def __init__(self, account, position=None) -> None:
        self.account = account
        self.current_position = position

    def owned_account(self, *_args, **_kwargs):
        return self.account

    def order_by_idempotency(self, *_args):
        return None

    def position(self, *_args, **_kwargs):
        return self.current_position


def account(cash: str = "1000000") -> VirtualAccount:
    return VirtualAccount(id=uuid4(), user_id=1, account_name="test", initial_cash=Decimal(cash), cash_balance=Decimal(cash), status="ACTIVE")


def request(side: str, quantity: int = 10) -> OrderCreateRequest:
    return OrderCreateRequest(account_id=uuid4(), stock_code="005930", side=side, quantity=quantity, idempotency_key=f"test-key-{side}-{quantity}")


def service(acc, position=None, price="70000"):
    session = FakeSession()
    svc = TradingService(session, FixedMarket(price))
    svc.repo = FakeRepo(acc, position)
    return svc, session


def test_buy_updates_average_cash_execution_and_ledger() -> None:
    acc = account()
    existing = Position(account_id=acc.id, stock_code="005930", quantity=10, average_price=Decimal("60000"), realized_profit=0)
    svc, session = service(acc, existing)
    order = svc.execute_market_order(1, request("BUY", 10))
    assert order.status == "FILLED"
    assert existing.quantity == 20
    assert existing.average_price == Decimal("65000.0000")
    assert acc.cash_balance == Decimal("300000.00")
    assert len([x for x in session.added if isinstance(x, Execution)]) == 1
    ledger = next(x for x in session.added if isinstance(x, CashLedger))
    assert ledger.amount == Decimal("-700000.00")
    assert ledger.balance_after == Decimal("300000.00")


def test_sell_updates_quantity_cash_and_realized_profit() -> None:
    acc = account("100000")
    existing = Position(account_id=acc.id, stock_code="005930", quantity=10, average_price=Decimal("60000"), realized_profit=0)
    svc, _ = service(acc, existing, "70000")
    svc.execute_market_order(1, request("SELL", 4))
    assert existing.quantity == 6
    assert existing.realized_profit == Decimal("40000.00")
    assert acc.cash_balance == Decimal("380000.00")


def test_buy_rejects_insufficient_cash_without_writes() -> None:
    svc, session = service(account("1000"))
    with pytest.raises(ServiceError, match="현금") as error:
        svc.execute_market_order(1, request("BUY", 1))
    assert error.value.code == "INSUFFICIENT_CASH"
    assert session.added == []


def test_sell_rejects_insufficient_position_without_writes() -> None:
    acc = account()
    position = Position(account_id=acc.id, stock_code="005930", quantity=1, average_price=Decimal("60000"), realized_profit=0)
    svc, session = service(acc, position)
    with pytest.raises(ServiceError, match="보유수량") as error:
        svc.execute_market_order(1, request("SELL", 2))
    assert error.value.code == "INSUFFICIENT_POSITION"
    assert session.added == []
