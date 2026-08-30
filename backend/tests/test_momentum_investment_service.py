"""모멘텀 Snapshot 목표 비중 발행과 최초 AUTO 체결 정책을 검증한다."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.services.momentum_investment import MomentumInvestmentService


class FakeSession:
    def __init__(self, *, position_count: int = 0, existing_order_keys=()) -> None:
        self.targets = []
        self.commits = 0
        self.position_count = position_count
        self.existing_order_keys = list(existing_order_keys)
        self.scalars_calls = 0

    def scalar(self, _query):
        return self.position_count

    def scalars(self, _query):
        self.scalars_calls += 1
        # apply() checks existing snapshot orders before publishing targets.
        # Rebalance() only needs the target query, so keep that path empty.
        if self.existing_order_keys and self.scalars_calls == 1:
            return self.existing_order_keys
        return []

    def add_all(self, values) -> None:
        self.targets.extend(values)

    def add(self, _value) -> None:
        pass

    def delete(self, _value) -> None:
        pass

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        self.commits += 1


class FakeRepo:
    def __init__(self, account, *, rebalance_run=None, empty_positions=False) -> None:
        self.account = account
        self.rebalance_run = rebalance_run
        self.empty_positions = empty_positions

    def owned_account(self, *_args, **_kwargs):
        return self.account

    def momentum_rebalance_run(self, *_args, **_kwargs):
        return self.rebalance_run

    def quarter_end_trade_date(self, *_args, **_kwargs):
        return date(2026, 9, 30)

    def positions(self, _account_id):
        return [] if self.empty_positions else [SimpleNamespace(stock_code="000001", quantity=Decimal("1"))]


class FixedMarket:
    def get_price(self, _stock_code):
        return Decimal("1000"), None, "TEST"


class FakeTradingService:
    def __init__(self) -> None:
        self.market = FixedMarket()
        self.requests = []

    def execute_market_order(self, user_id, request):
        self.requests.append((user_id, request))


class FakeSnapshotService:
    def __init__(self, *, source: str = "generated", is_stale: bool = False) -> None:
        self.snapshot = SimpleNamespace(
            as_of=date(2026, 9, 30),
            model_version="risk-adjusted-momentum-v2",
            source=source,
            is_stale=is_stale,
            recommendations=[
                SimpleNamespace(symbol=f"{index:06d}", target_weight=0.05)
                for index in range(19)
            ],
        )

    def latest(self):
        return self.snapshot


def service(
    operation_mode: str = "AUTO",
    *,
    position_count: int = 0,
    existing_order_keys=(),
    rebalance_run=None,
    empty_positions=False,
    **snapshot_options,
):
    account = SimpleNamespace(
        id=uuid4(),
        selected_strategy_id="momentum",
        operation_mode=operation_mode,
        initial_cash=Decimal("10000000"),
        invested_principal=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
    )
    session = FakeSession(
        position_count=position_count,
        existing_order_keys=existing_order_keys,
    )
    trading = FakeTradingService()
    result = MomentumInvestmentService(
        session,  # type: ignore[arg-type]
        snapshot_service=FakeSnapshotService(**snapshot_options),  # type: ignore[arg-type]
        trading_service=trading,  # type: ignore[arg-type]
    )
    result.repo = FakeRepo(account, rebalance_run=rebalance_run, empty_positions=empty_positions)  # type: ignore[assignment]
    return result, session, trading


def test_auto_account_publishes_targets_and_executes_initial_orders() -> None:
    momentum, session, trading = service()

    response = momentum.apply(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert response.status == "APPLIED"
    assert response.orders_created == 19
    assert {target.stock_code for target in session.targets} == {f"{index:06d}" for index in range(19)}
    assert sum((target.target_weight for target in session.targets), Decimal("0")) == Decimal("0.950")
    assert [request.quantity for _, request in trading.requests] == [Decimal("500.00000000")] * 19


def test_initial_orders_use_invested_principal_not_stale_initial_cash() -> None:
    momentum, _, trading = service()
    momentum.repo.account.initial_cash = Decimal("100000000")  # type: ignore[attr-defined]
    momentum.repo.account.invested_principal = Decimal("1000000")  # type: ignore[attr-defined]

    momentum.apply(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert [request.quantity for _, request in trading.requests] == [Decimal("50.00000000")] * 19


def test_apply_does_not_restore_a_strategy_changed_after_momentum_onboarding() -> None:
    momentum, session, trading = service()
    momentum.repo.account.selected_strategy_id = "value"  # type: ignore[attr-defined]

    with pytest.raises(ServiceError) as error:
        momentum.apply(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert error.value.code == "MOMENTUM_STRATEGY_REQUIRED"
    assert momentum.repo.account.selected_strategy_id == "value"  # type: ignore[attr-defined]
    assert session.commits == 0
    assert trading.requests == []


def test_semi_auto_account_only_publishes_proposals() -> None:

    momentum, session, trading = service("SEMI_AUTO")

    response = momentum.apply(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert response.status == "PROPOSAL_ONLY"
    assert len(session.targets) == 19
    assert trading.requests == []


def test_partial_initial_orders_resume_with_original_investment_amount() -> None:
    first_key = "momentum-2026-09-30-000000"
    momentum, _, trading = service(
        position_count=1,
        existing_order_keys=[first_key],
    )

    response = momentum.apply(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert response.status == "APPLIED"
    assert response.orders_created == 18
    assert [request.stock_code for _, request in trading.requests] == [f"{index:06d}" for index in range(1, 19)]
    assert trading.requests[0][1].quantity == Decimal("500.00000000")


def test_existing_unrelated_portfolio_is_not_overwritten() -> None:
    momentum, _, trading = service(position_count=1)

    response = momentum.apply(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert response.status == "PROPOSAL_ONLY"
    assert response.orders_created == 0
    assert trading.requests == []


@pytest.mark.parametrize("options", [{"source": "fallback"}, {"is_stale": True}])
def test_fallback_or_stale_snapshot_is_not_applied(options) -> None:
    momentum, _, trading = service(**options)

    with pytest.raises(ServiceError) as error:
        momentum.apply(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert error.value.code == "MODEL_RECOMMENDATION_NOT_APPLICABLE"
    assert trading.requests == []


def test_rebalance_rejects_a_new_snapshot_after_the_quarter_was_executed() -> None:
    momentum, _, trading = service(
        position_count=1,
        rebalance_run=SimpleNamespace(
            snapshot_date=date(2026, 8, 20),
            status="RUNNING",
        ),
    )

    with pytest.raises(ServiceError) as error:
        momentum.rebalance(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert error.value.code == "MOMENTUM_QUARTER_ALREADY_EXECUTED"
    assert trading.requests == []


def test_rebalance_completed_run_is_noop_for_the_same_snapshot() -> None:
    momentum, _, trading = service(
        position_count=1,
        rebalance_run=SimpleNamespace(
            snapshot_date=date(2026, 9, 30),
            status="COMPLETED",
        ),
    )

    response = momentum.rebalance(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert response.status == "ALREADY_APPLIED"
    assert response.orders_created == 0
    assert trading.requests == []


def test_rebalance_completed_run_rejects_a_different_snapshot_in_same_quarter() -> None:
    momentum, _, trading = service(
        position_count=1,
        rebalance_run=SimpleNamespace(
            snapshot_date=date(2026, 8, 20),
            status="COMPLETED",
        ),
    )

    with pytest.raises(ServiceError) as error:
        momentum.rebalance(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert error.value.code == "MOMENTUM_QUARTER_ALREADY_EXECUTED"
    assert trading.requests == []


def test_rebalance_rejects_a_mid_quarter_snapshot() -> None:
    momentum, _, trading = service(position_count=1)
    momentum.snapshot_service.snapshot.as_of = date(2026, 8, 25)

    with pytest.raises(ServiceError) as error:
        momentum.rebalance(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert error.value.code == "MOMENTUM_QUARTER_END_SNAPSHOT_REQUIRED"
    assert trading.requests == []


def test_rebalance_empty_account_delegates_before_creating_run() -> None:
    momentum, session, trading = service(empty_positions=True)

    response = momentum.rebalance(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert response.status == "APPLIED"
    assert response.orders_created == 19
    assert trading.requests
    # The fake apply path has no persisted run, but importantly it did not
    # attempt to mutate a flushed run after TradingService rollback.
    assert session.commits > 0
