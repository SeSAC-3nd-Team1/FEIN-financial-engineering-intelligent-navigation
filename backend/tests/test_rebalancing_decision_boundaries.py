from datetime import date, datetime, UTC
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import ServiceError
from app.schemas.api import RebalancingDecisionCreateRequest
from app.services import portfolio_analytics
from app.services.portfolio_analytics import PortfolioAnalyticsService

PROPOSAL_A = "low|005930|SELL|20|15|5|50000|2026-08-25"
PROPOSAL_B = "low|005930|SELL|21|15|6|60000|2026-08-25"


def _request(
    proposal_key: str, key: str = "request-1"
) -> RebalancingDecisionCreateRequest:
    return RebalancingDecisionCreateRequest(
        account_id=ACCOUNT_ID,
        stock_code="005930",
        proposal_key=proposal_key,
        decision="ACCEPTED",
        idempotency_key=key,
    )


ACCOUNT_ID = uuid4()
ACCOUNT = SimpleNamespace(id=ACCOUNT_ID, selected_strategy_id="low")


def _decision(proposal_key: str, decision: str = "ACCEPTED"):
    return SimpleNamespace(
        id=uuid4(),
        account_id=ACCOUNT_ID,
        proposal_key=proposal_key,
        strategy_id="low",
        stock_code="005930",
        stock_name="삼성전자",
        action="SELL",
        current_weight=Decimal("20"),
        target_weight=Decimal("15"),
        weight_diff=Decimal("5"),
        recommended_amount=Decimal("50000"),
        decision=decision,
        baseline_snapshot_date=date(2026, 8, 25),
        baseline_total_assets=Decimal("1000000"),
        created_at=datetime(2026, 8, 25, tzinfo=UTC),
    )


def test_same_idempotency_key_with_different_proposal_is_conflict() -> None:
    class Trading:
        def owned_account(self, *_):
            return ACCOUNT

        def decision_by_idempotency(self, *_):
            return _decision(PROPOSAL_A)

    service = PortfolioAnalyticsService.__new__(PortfolioAnalyticsService)
    service.trading = Trading()

    with pytest.raises(ServiceError) as error:
        service.record_decision(1, _request(PROPOSAL_B))

    assert error.value.code == "IDEMPOTENCY_CONFLICT"


def _proposal():
    return SimpleNamespace(
        proposal_key=PROPOSAL_A,
        stock_code="005930",
        stock_name="삼성전자",
        action="SELL",
        current_weight=Decimal("20"),
        target_weight=Decimal("15"),
        weight_diff=Decimal("5"),
        recommended_amount=Decimal("50000"),
    )


def _patch_portfolio(monkeypatch) -> None:
    monkeypatch.setattr(
        portfolio_analytics,
        "PortfolioService",
        lambda _: SimpleNamespace(
            evaluate=lambda *_: SimpleNamespace(
                rebalancing_proposals=[_proposal()],
                positions=[],
                total_assets=Decimal("1000000"),
            )
        ),
    )


def test_stale_proposal_is_rejected_before_persisting(monkeypatch) -> None:

    class Trading:
        def owned_account(self, *_):
            return ACCOUNT

        def decision_by_idempotency(self, *_):
            return None

    _patch_portfolio(monkeypatch)
    service = PortfolioAnalyticsService.__new__(PortfolioAnalyticsService)
    service.session = SimpleNamespace()
    service.trading = Trading()

    with pytest.raises(ServiceError) as error:
        service.record_decision(1, _request(PROPOSAL_B))

    assert error.value.code == "PROPOSAL_STALE"


def test_integrity_error_race_recovers_same_idempotent_decision(monkeypatch) -> None:
    concurrent = _decision(PROPOSAL_A)

    class Trading:
        idempotency_calls = 0

        def owned_account(self, *_):
            return ACCOUNT

        def decision_by_idempotency(self, *_):
            self.idempotency_calls += 1
            return concurrent if self.idempotency_calls > 1 else None

        def decision_by_proposal(self, *_):
            return None

        def add_decision(self, _decision):
            return None

        def latest_snapshot(self, *_):
            return None

    class Session:
        rolled_back = False

        def commit(self):
            raise IntegrityError("insert", {}, Exception("duplicate"))

        def rollback(self):
            self.rolled_back = True

    _patch_portfolio(monkeypatch)
    service = PortfolioAnalyticsService.__new__(PortfolioAnalyticsService)
    service.session = Session()
    service.trading = Trading()

    result = service.record_decision(1, _request(PROPOSAL_A))

    assert result.id == concurrent.id
    assert service.session.rolled_back is True


def test_integrity_error_race_reports_opposite_proposal_decision(monkeypatch) -> None:
    concurrent = _decision(PROPOSAL_A, decision="HELD")

    class Trading:
        proposal_calls = 0

        def owned_account(self, *_):
            return ACCOUNT

        def decision_by_idempotency(self, *_):
            return None

        def decision_by_proposal(self, *_):
            self.proposal_calls += 1
            return concurrent if self.proposal_calls > 1 else None

        def add_decision(self, _decision):
            return None

    class Session:
        def commit(self):
            raise IntegrityError("insert", {}, Exception("duplicate"))

        def rollback(self):
            return None

    _patch_portfolio(monkeypatch)
    service = PortfolioAnalyticsService.__new__(PortfolioAnalyticsService)
    service.session = Session()
    service.trading = Trading()

    with pytest.raises(ServiceError) as error:
        service.record_decision(1, _request(PROPOSAL_A))

    assert error.value.code == "REBALANCING_PROPOSAL_ALREADY_DECIDED"
