"""PostgreSQL-backed Momentum rebalance transaction tests.

These tests intentionally use the real ORM and TradingService.  They are
skipped for the fast unit-test job and run in the integration PostgreSQL job.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import (
    CashLedger,
    Execution,
    MomentumRebalanceRun,
    Order,
    Position,
    StrategyTargetWeight,
    User,
    VirtualAccount,
)
from app.schemas.api import OrderCreateRequest
from app.services.momentum_investment import MomentumInvestmentService
from app.services.trading import TradingService


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1", reason="RUN_INTEGRATION=1 required"
)

SNAPSHOT_DATE = date(2026, 6, 30)
SYMBOLS = [f"{index:06d}" for index in range(19)]


class Snapshot:
    as_of = SNAPSHOT_DATE
    source = "generated"
    is_stale = False
    model_version = "risk-adjusted-momentum-v2"
    recommendations = [
        type("Recommendation", (), {"symbol": symbol, "target_weight": 0.05})
        for symbol in SYMBOLS
    ]


class SnapshotService:
    def latest(self):
        return Snapshot()


class DeterministicMarket:
    def __init__(self, price: Decimal = Decimal("100")):
        self.price = price

    def get_price(self, _stock_code):
        return self.price, None, "TEST"


class FailOnceOnBuy(TradingService):
    def __init__(self, session, market):
        super().__init__(session, market=market)
        self.failed = False

    def execute_market_order(self, user_id, request):
        if request.side == "BUY" and not self.failed:
            self.failed = True
            raise RuntimeError("forced BUY failure")
        return super().execute_market_order(user_id, request)


def _create_fixture(session):
    user = User(
        user_id=f"mi{uuid4().hex[:14]}",
        password_hash="test",
        name="통합테스트",
        birthdate="900101",
        phone_number=f"010{uuid4().int % 100000000:08d}",
        email=f"{uuid4().hex}@example.com",
        email_verified_at=datetime.now(timezone.utc),
        account_status="ACTIVE",
        active_operation_mode="AUTO",
    )
    session.add(user)
    session.flush()
    account = VirtualAccount(
        user_id=user.id,
        operation_mode="AUTO",
        account_name="momentum integration",
        initial_cash=Decimal("1000000"),
        cash_balance=Decimal("50000"),
        invested_principal=Decimal("950000"),
        status="ACTIVE",
        selected_strategy_id="momentum",
    )
    session.add(account)
    session.flush()
    for symbol, quantity in (("000000", 3000), ("000001", 3000), ("000002", 3500)):
        session.add(
            Position(
                account_id=account.id,
                stock_code=symbol,
                quantity=Decimal(quantity),
                average_price=Decimal("100"),
                realized_profit=Decimal("0"),
            )
        )
    session.commit()
    return user, account


def _cleanup(session, user, account) -> None:
    session.execute(delete(Execution).where(Execution.account_id == account.id))
    session.execute(delete(CashLedger).where(CashLedger.account_id == account.id))
    session.execute(delete(Order).where(Order.account_id == account.id))
    session.execute(delete(Position).where(Position.account_id == account.id))
    session.execute(delete(MomentumRebalanceRun).where(MomentumRebalanceRun.account_id == account.id))
    session.execute(delete(StrategyTargetWeight).where(StrategyTargetWeight.effective_from == SNAPSHOT_DATE))
    session.execute(delete(VirtualAccount).where(VirtualAccount.id == account.id))
    session.delete(user)
    session.commit()


def _service(session, trading):
    service = MomentumInvestmentService(
        session,
        snapshot_service=SnapshotService(),
        trading_service=trading,
    )
    # Calendar availability is tested against the real repository separately;
    # this test isolates the actual order/ORM transaction path.
    service.repo.quarter_end_trade_date = lambda *_args: SNAPSHOT_DATE
    return service


def test_rebalance_uses_real_trading_service_and_resumes_immutable_plan():
    market = DeterministicMarket()
    with SessionLocal() as session:
        user, account = _create_fixture(session)
        try:
            first = _service(session, FailOnceOnBuy(session, market))
            with pytest.raises(RuntimeError, match="forced BUY failure"):
                first.rebalance(user.id, account.id)

            failed_run = session.scalar(
                select(MomentumRebalanceRun).where(MomentumRebalanceRun.account_id == account.id)
            )
            assert failed_run.status == "RUNNING"
            original_plan = failed_run.plan
            assert original_plan
            failed_orders = list(session.scalars(select(Order).where(Order.account_id == account.id)))
            failed_sell_ids = {order.id for order in failed_orders if order.side == "SELL"}
            assert failed_sell_ids
            assert [leg["side"] for leg in original_plan] == sorted(
                (leg["side"] for leg in original_plan), key=lambda side: side != "SELL"
            )
            assert session.scalar(select(Execution).where(Execution.account_id == account.id)) is not None

            # A retry must use the persisted quantities even after market prices change.
            # Change the quote without making the persisted plan unaffordable;
            # the quantity must still come from the original plan, not from a
            # fresh delta calculation at this new price.
            market.price = Decimal("101")
            retry = _service(session, TradingService(session, market=market))
            retry.rebalance(user.id, account.id)

            completed = session.scalar(
                select(MomentumRebalanceRun).where(MomentumRebalanceRun.account_id == account.id)
            )
            assert completed.status == "COMPLETED"
            assert completed.plan == original_plan
            orders = list(session.scalars(select(Order).where(Order.account_id == account.id).order_by(Order.requested_at, Order.id)))
            assert len(orders) == len(original_plan)
            assert failed_sell_ids == {order.id for order in orders if order.side == "SELL"}
            assert len({order.idempotency_key for order in orders}) == len(orders)
            assert {
                (order.stock_code, order.side, Decimal(order.quantity)) for order in orders
            } == {
                (leg["symbol"], leg["side"], Decimal(leg["quantity"])) for leg in original_plan
            }
            first_buy = next(index for index, order in enumerate(orders) if order.side == "BUY")
            assert all(order.side == "SELL" for order in orders[:first_buy])
            assert all(
                session.scalar(select(Execution).where(Execution.order_id == order.id)) is not None
                for order in orders
            )
            assert session.scalar(select(CashLedger).where(CashLedger.account_id == account.id)) is not None

            before = len(orders)
            response = retry.rebalance(user.id, account.id)
            assert response.status == "ALREADY_APPLIED"
            assert len(list(session.scalars(select(Order).where(Order.account_id == account.id)))) == before
        finally:
            _cleanup(session, user, account)


def test_empty_account_rebalance_uses_real_trading_service_transaction():
    with SessionLocal() as session:
        user, account = _create_fixture(session)
        session.execute(delete(Position).where(Position.account_id == account.id))
        account.cash_balance = Decimal("1000000")
        session.commit()
        try:
            service = _service(session, TradingService(session, market=DeterministicMarket()))
            response = service.rebalance(user.id, account.id)

            assert response.status == "APPLIED"
            assert session.scalar(select(Position).where(Position.account_id == account.id)) is not None
            run = session.scalar(
                select(MomentumRebalanceRun).where(MomentumRebalanceRun.account_id == account.id)
            )
            assert run is not None
            assert run.status == "COMPLETED"
            before = len(list(session.scalars(select(Order).where(Order.account_id == account.id))))
            again = service.rebalance(user.id, account.id)
            assert again.status == "ALREADY_APPLIED"
            assert len(list(session.scalars(select(Order).where(Order.account_id == account.id)))) == before
        finally:
            _cleanup(session, user, account)
