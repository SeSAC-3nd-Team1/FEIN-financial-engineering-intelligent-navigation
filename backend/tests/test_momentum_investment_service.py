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
        # 첫 조회는 같은 기준일의 목표 비중, 두 번째 조회는 현재 스냅샷 주문 키다.
        return [] if self.scalars_calls == 1 else self.existing_order_keys

    def add_all(self, values) -> None:
        self.targets.extend(values)

    def commit(self) -> None:
        self.commits += 1


class FakeRepo:
    def __init__(self, account) -> None:
        self.account = account

    def owned_account(self, *_args, **_kwargs):
        return self.account


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
            as_of=date(2026, 8, 25),
            source=source,
            is_stale=is_stale,
            recommendations=[
                SimpleNamespace(symbol="005930", target_weight=0.475),
                SimpleNamespace(symbol="000660", target_weight=0.475),
            ],
        )

    def latest(self):
        return self.snapshot


def service(
    operation_mode: str = "AUTO",
    *,
    position_count: int = 0,
    existing_order_keys=(),
    **snapshot_options,
):
    account = SimpleNamespace(
        id=uuid4(),
        selected_strategy_id="momentum",
        operation_mode=operation_mode,
        initial_cash=Decimal("10000000"),
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
    result.repo = FakeRepo(account)  # type: ignore[assignment]
    return result, session, trading


def test_auto_account_publishes_targets_and_executes_initial_orders() -> None:
    momentum, session, trading = service()

    response = momentum.apply(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert response.status == "APPLIED"
    assert response.orders_created == 2
    assert {target.stock_code for target in session.targets} == {"005930", "000660"}
    assert sum((target.target_weight for target in session.targets), Decimal("0")) == Decimal("0.950")
    assert [request.quantity for _, request in trading.requests] == [
        Decimal("4750.00000000"),
        Decimal("4750.00000000"),
    ]


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
    assert len(session.targets) == 2
    assert trading.requests == []


def test_partial_initial_orders_resume_with_original_investment_amount() -> None:
    first_key = "momentum-2026-08-25-005930"
    momentum, _, trading = service(
        position_count=1,
        existing_order_keys=[first_key],
    )

    response = momentum.apply(7, momentum.repo.account.id)  # type: ignore[attr-defined]

    assert response.status == "APPLIED"
    assert response.orders_created == 1
    assert [request.stock_code for _, request in trading.requests] == ["000660"]
    assert trading.requests[0][1].quantity == Decimal("4750.00000000")


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
