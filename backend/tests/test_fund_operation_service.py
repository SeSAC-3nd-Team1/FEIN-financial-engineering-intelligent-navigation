"""가상 추가투자·출금의 배분, 원금, 단일 transaction 계약을 검증한다."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.models import CashLedger, FundOperation, FundOperationOrder
from app.schemas.api import FundOperationRequest
from app.services.funds import FundOperationService


NOW = datetime(2026, 8, 27, tzinfo=UTC)


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, value) -> None:
        self.added.append(value)

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FixedMarket:
    def __init__(self, prices: dict[str, str]) -> None:
        self.prices = {code: Decimal(price) for code, price in prices.items()}

    def get_price(self, stock_code: str):
        return self.prices[stock_code], NOW, "TEST"


class FakeRepository:
    def __init__(self, session: FakeSession, account, positions, targets) -> None:
        self.session = session
        self.account = account
        self._positions = positions
        self.targets = targets

    def owned_account(self, account_id, user_id, *, lock=False):
        return self.account if account_id == self.account.id and user_id == 7 else None

    def positions(self, _account_id):
        return self._positions

    def target_weights(self, _strategy_id, _effective_on: date):
        return self.targets

    def fund_operation_by_idempotency(self, account_id, key):
        return next(
            (
                value
                for value in self.session.added
                if isinstance(value, FundOperation)
                and value.account_id == account_id
                and value.idempotency_key == key
            ),
            None,
        )

    def fund_operation_orders(self, operation_id):
        links = [
            value
            for value in self.session.added
            if isinstance(value, FundOperationOrder)
            and value.fund_operation_id == operation_id
        ]
        orders = {
            order.id: order
            for order in self.session.added
            if getattr(order, "kind", None) == "order"
        }
        return [(link, orders[link.order_id]) for link in links]


class FakeTrading:
    def __init__(self, session: FakeSession, positions) -> None:
        self.session = session
        self.positions = positions

    def execute_locked_market_order(self, account, request, price):
        position = next(
            (item for item in self.positions if item.stock_code == request.stock_code),
            None,
        )
        total = (Decimal(price) * request.quantity).quantize(Decimal("0.01"))
        if request.side == "BUY":
            if position is None:
                position = SimpleNamespace(
                    stock_code=request.stock_code,
                    quantity=Decimal("0"),
                    average_price=Decimal(price),
                    realized_profit=Decimal("0"),
                )
                self.positions.append(position)
            position.quantity += request.quantity
            account.cash_balance -= total
        else:
            assert position is not None
            position.quantity -= request.quantity
            account.cash_balance += total
        order = SimpleNamespace(
            kind="order",
            id=uuid4(),
            stock_code=request.stock_code,
            side=request.side,
            quantity=request.quantity,
            requested_price=Decimal(price),
        )
        self.session.add(order)
        return order


def build_service(*, cash="100", principal="1000", positions=None, targets=None):
    session = FakeSession()
    account = SimpleNamespace(
        id=uuid4(),
        user_id=7,
        status="ACTIVE",
        selected_strategy_id="low",
        initial_cash=Decimal("1000"),
        invested_principal=Decimal(principal),
        cash_balance=Decimal(cash),
    )
    positions = positions or []
    prices = {position.stock_code: "100" for position in positions}
    prices.update({code: "100" for code in (targets or {})})
    trading = FakeTrading(session, positions)
    service = FundOperationService(
        session,  # type: ignore[arg-type]
        market=FixedMarket(prices),  # type: ignore[arg-type]
        trading=trading,  # type: ignore[arg-type]
    )
    service.repo = FakeRepository(session, account, positions, targets or {})  # type: ignore[assignment]
    return service, session, account, positions


def test_additional_investment_buys_only_new_money_by_target_weight() -> None:
    positions = [
        SimpleNamespace(
            stock_code="005930",
            quantity=Decimal("5"),
            average_price=Decimal("100"),
            realized_profit=Decimal("0"),
        )
    ]
    service, session, account, positions = build_service(
        positions=positions,
        targets={"005930": Decimal("0.60"), "000660": Decimal("0.40")},
    )

    response = service.add_investment(
        7,
        account.id,
        FundOperationRequest(amount="1000", idempotency_key="add-money-0001"),
    )

    assert response.status == "COMPLETED"
    assert response.settlement_mode == "VIRTUAL"
    assert account.invested_principal == Decimal("2000.00")
    assert {trade.stock_code: trade.transaction_amount for trade in response.trades} == {
        "000660": Decimal("400.00"),
        "005930": Decimal("600.00"),
    }
    assert next(item for item in positions if item.stock_code == "005930").quantity == Decimal("11.00000000")
    assert session.commits == 1


def test_withdrawal_sells_current_positions_proportionally_and_reduces_assets() -> None:
    positions = [
        SimpleNamespace(
            stock_code="005930",
            quantity=Decimal("6"),
            average_price=Decimal("100"),
            realized_profit=Decimal("0"),
        ),
        SimpleNamespace(
            stock_code="000660",
            quantity=Decimal("4"),
            average_price=Decimal("100"),
            realized_profit=Decimal("0"),
        ),
    ]
    service, session, account, _ = build_service(
        cash="100", principal="1000", positions=positions
    )

    response = service.withdraw(
        7,
        account.id,
        FundOperationRequest(amount="500", idempotency_key="withdraw-0001"),
    )

    assert {trade.stock_code: trade.transaction_amount for trade in response.trades} == {
        "000660": Decimal("200.00"),
        "005930": Decimal("300.00"),
    }
    assert response.portfolio.total_assets == Decimal("600.00")
    assert response.principal_after == Decimal("545.45")
    assert account.cash_balance == Decimal("100.00")
    withdrawal = next(
        item
        for item in session.added
        if isinstance(item, CashLedger) and item.transaction_type == "WITHDRAWAL"
    )
    assert withdrawal.amount == Decimal("-500")
    assert session.commits == 1


def test_fund_operation_idempotency_key_rejects_different_request() -> None:
    service, session, account, _ = build_service(
        targets={"005930": Decimal("1")}
    )
    session.add(
        FundOperation(
            id=uuid4(),
            account_id=account.id,
            operation_type="ADDITIONAL_INVESTMENT",
            status="COMPLETED",
            requested_amount=Decimal("100"),
            executed_amount=Decimal("100"),
            principal_before=Decimal("1000"),
            principal_after=Decimal("1100"),
            total_assets_before=Decimal("1000"),
            total_assets_after=Decimal("1100"),
            idempotency_key="same-key-0001",
            completed_at=NOW,
        )
    )

    with pytest.raises(ServiceError) as error:
        service.withdraw(
            7,
            account.id,
            FundOperationRequest(amount="100", idempotency_key="same-key-0001"),
        )

    assert error.value.code == "FUND_OPERATION_IDEMPOTENCY_CONFLICT"


def test_multi_stock_operation_rolls_back_as_one_unit_on_order_failure() -> None:
    service, session, account, _ = build_service(
        targets={"005930": Decimal("0.50"), "000660": Decimal("0.50")}
    )
    original = service.trading.execute_locked_market_order
    calls = 0

    def fail_second_order(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second order failed")
        return original(*args, **kwargs)

    service.trading.execute_locked_market_order = fail_second_order

    with pytest.raises(RuntimeError, match="second order failed"):
        service.add_investment(
            7,
            account.id,
            FundOperationRequest(amount="1000", idempotency_key="add-rollback-01"),
        )

    assert session.commits == 0
    assert session.rollbacks == 2
