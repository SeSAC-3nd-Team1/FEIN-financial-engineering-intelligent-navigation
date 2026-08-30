"""물림방지 알고리즘 스냅샷의 목표 비중과 주문 적용을 검증한다."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.services.loss_avoidance_investment import LossAvoidanceInvestmentService


class FakeSession:
    def __init__(self) -> None:
        self.targets = []
        self.scalars_calls = 0

    def scalar(self, _query):
        return 0

    def scalars(self, _query):
        self.scalars_calls += 1
        return []

    def add_all(self, values):
        self.targets.extend(values)

    def commit(self):
        pass


class FakeTrading:
    market = SimpleNamespace(get_price=lambda _symbol: (Decimal("1000"), None, "TEST"))

    def __init__(self) -> None:
        self.requests = []

    def execute_market_order(self, user_id, request):
        self.requests.append((user_id, request))


class FakeSnapshot:
    def __init__(
        self,
        model_version: str = "algorithm-v2.4-fix2",
        is_stale: bool = False,
    ) -> None:
        self.value = SimpleNamespace(
            as_of=date(2026, 8, 28),
            source="generated",
            is_stale=is_stale,
            model_version=model_version,
            recommendations=[
                SimpleNamespace(symbol="005930", target_weight=0.4),
                SimpleNamespace(symbol="000660", target_weight=0.3),
            ],
        )

    def latest(self):
        return self.value


def make_service(model_version: str = "algorithm-v2.4-fix2"):
    account = SimpleNamespace(
        id=uuid4(),
        selected_strategy_id="low",
        operation_mode="AUTO",
        initial_cash=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
    )
    session = FakeSession()
    trading = FakeTrading()
    service = LossAvoidanceInvestmentService(
        session,  # type: ignore[arg-type]
        snapshot_service=FakeSnapshot(model_version),  # type: ignore[arg-type]
        trading_service=trading,  # type: ignore[arg-type]
    )
    service.repo = SimpleNamespace(owned_account=lambda *_args, **_kwargs: account)
    return service, session, trading, account


def test_algorithm_v23_targets_are_published_and_executed() -> None:
    service, session, trading, account = make_service()

    response = service.apply(7, account.id)

    assert response.strategy_id == "low"
    assert response.status == "APPLIED"
    assert sum((target.target_weight for target in session.targets), Decimal("0")) == Decimal("0.7")
    assert [request.quantity for _, request in trading.requests] == [
        Decimal("4000.00000000"),
        Decimal("3000.00000000"),
    ]


def test_non_algorithm_snapshot_is_rejected() -> None:
    service, _, trading, account = make_service("another-model")

    with pytest.raises(ServiceError) as raised:
        service.apply(7, account.id)

    assert raised.value.code == "LOSS_AVOIDANCE_SNAPSHOT_NOT_APPLICABLE"
    assert trading.requests == []


def test_stale_generated_snapshot_can_seed_an_evening_signup() -> None:
    service, session, trading, account = make_service()
    service.snapshot_service = FakeSnapshot(is_stale=True)

    response = service.apply(7, account.id)

    assert response.status == "APPLIED"
    assert len(session.targets) == 2
    assert len(trading.requests) == 2
