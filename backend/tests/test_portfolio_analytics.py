"""실제 feature 산식과 리밸런싱 판단 기록을 검증한다."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.api import RebalancingDecisionCreateRequest
from app.services import portfolio_analytics
from app.services.portfolio_analytics import (
    PortfolioAnalyticsService,
    _returns,
    calculate_defense,
    calculate_diversification,
    calculate_financial_health,
    calculate_growth,
    calculate_stability,
)


def test_unadjusted_corporate_action_resets_feature_return_baseline() -> None:
    points = [
        SimpleNamespace(
            trade_date=date(2026, 1, 1), close_price=Decimal("100"), listed_shares=100
        ),
        SimpleNamespace(
            trade_date=date(2026, 1, 2), close_price=Decimal("50"), listed_shares=200
        ),
        SimpleNamespace(
            trade_date=date(2026, 1, 3), close_price=Decimal("55"), listed_shares=200
        ),
    ]

    returns = _returns(points, "close_price", share_attribute="listed_shares")

    assert date(2026, 1, 2) not in returns
    assert returns[date(2026, 1, 3)] == pytest.approx(0.1)


def test_feature_scores_use_real_price_and_financial_inputs() -> None:
    start = date(2026, 1, 1)
    stock_returns = {
        start + timedelta(days=index): (-0.01 if index % 2 else 0.012)
        for index in range(45)
    }
    benchmark_returns = {
        day: (-0.008 if index % 2 else 0.004) for index, day in enumerate(stock_returns)
    }
    other_returns = {day: -value for day, value in stock_returns.items()}
    latest = SimpleNamespace(
        business_year="2025",
        revenue=Decimal("120"),
        operating_income=Decimal("24"),
        total_assets=Decimal("200"),
        total_equity=Decimal("120"),
        operating_cash_flow=Decimal("20"),
    )
    previous = SimpleNamespace(
        business_year="2024",
        revenue=Decimal("100"),
        operating_income=Decimal("20"),
    )

    stability, _ = calculate_stability(stock_returns)
    health, _ = calculate_financial_health(latest)
    growth, _ = calculate_growth(latest, previous)
    defense, _ = calculate_defense(stock_returns, benchmark_returns)
    diversification, _ = calculate_diversification(stock_returns, other_returns)

    assert stability is not None and 0 <= stability <= 100
    assert health == 93
    assert growth == 100
    assert defense is not None and 0 <= defense <= 100
    assert diversification == 100


def test_feature_axes_are_unavailable_when_samples_are_incomplete() -> None:
    assert calculate_stability({date(2026, 1, 1): 0.01})[0] is None
    assert calculate_defense({}, {})[0] is None
    assert calculate_diversification({}, {})[0] is None
    assert (
        calculate_financial_health(
            SimpleNamespace(
                total_assets=None,
                total_equity=None,
                operating_cash_flow=None,
            )
        )[0]
        is None
    )


def test_record_decision_persists_server_side_proposal(monkeypatch) -> None:
    account_id = uuid4()
    account = SimpleNamespace(id=account_id, selected_strategy_id="low-volatility")
    proposal = SimpleNamespace(
        stock_code="005930",
        stock_name="삼성전자",
        action="SELL",
        current_weight=Decimal("20"),
        target_weight=Decimal("15"),
        weight_diff=Decimal("5"),
        recommended_amount=Decimal("50000"),
        proposal_key="low-volatility|005930|SELL|20|15|5|50000|2026-08-25",
    )

    class FakeTrading:
        def owned_account(self, *_args):
            return account

        def decision_by_idempotency(self, *_args):
            return None

        def decision_by_proposal(self, *_args):
            return None

        def latest_snapshot(self, *_args):
            return None

        def add_decision(self, decision):
            self.saved = decision

    class FakeSession:
        def commit(self):
            self.committed = True

        def refresh(self, decision):
            decision.id = uuid4()
            decision.created_at = datetime(2026, 8, 25, tzinfo=UTC)

        def rollback(self):
            raise AssertionError("successful decision must not roll back")

    monkeypatch.setattr(
        portfolio_analytics,
        "PortfolioService",
        lambda _session: SimpleNamespace(
            evaluate=lambda *_args: SimpleNamespace(
                rebalancing_proposals=[proposal],
                total_assets=Decimal("1012345.67"),
                positions=[
                    SimpleNamespace(price_as_of=datetime(2026, 8, 25, 6, tzinfo=UTC))
                ],
            )
        ),
    )
    service = PortfolioAnalyticsService.__new__(PortfolioAnalyticsService)
    service.session = FakeSession()
    service.trading = FakeTrading()
    request = RebalancingDecisionCreateRequest(
        account_id=account_id,
        stock_code="005930",
        proposal_key="low-volatility|005930|SELL|20|15|5|50000|2026-08-25",
        decision="ACCEPTED",
        idempotency_key="decision-1",
    )

    result = service.record_decision(1, request)

    assert result.current_weight == Decimal("20")
    assert result.baseline_snapshot_date == date(2026, 8, 25)
    assert service.trading.saved.baseline_total_assets == Decimal("1012345.67")
    assert service.trading.saved.stock_name == "삼성전자"
    assert service.session.committed is True
    assert service.trading.saved.proposal_key
