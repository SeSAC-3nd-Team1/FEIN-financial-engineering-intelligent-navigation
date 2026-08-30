"""AUTO와 SEMI_AUTO 계좌 비교 산식과 AI 부분 실패 경계를 검증한다."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.integrations.ai.portfolio_comparison_client import AIPortfolioComparisonResult
from app.services.portfolio_comparison import PortfolioComparisonService, build_comparison_series


def snapshot(observed_on: date, assets: str):
    return SimpleNamespace(snapshot_date=observed_on, total_assets=Decimal(assets))


def cash_flow(observed_on: date, amount: str, transaction_type: str = "DEPOSIT"):
    return SimpleNamespace(
        created_at=datetime.combine(observed_on, datetime.min.time(), UTC),
        amount=Decimal(amount),
        transaction_type=transaction_type,
    )


def account(mode: str):
    return SimpleNamespace(
        id=uuid4(),
        account_name="AI 자동투자" if mode == "AUTO" else "내 투자",
        operation_mode=mode,
        selected_strategy_id="low" if mode == "AUTO" else "balanced",
    )


class FakeRepository:
    def __init__(
        self,
        auto_account,
        my_account,
        auto_snapshots,
        my_snapshots,
        auto_cash_flows=None,
        my_cash_flows=None,
    ):
        self.accounts = {"AUTO": auto_account, "SEMI_AUTO": my_account}
        self.snapshots = {
            auto_account.id if auto_account else None: auto_snapshots,
            my_account.id if my_account else None: my_snapshots,
        }
        self.cash_flows = {
            auto_account.id if auto_account else None: auto_cash_flows or [],
            my_account.id if my_account else None: my_cash_flows or [],
        }

    def account_for_user(self, _user_id, operation_mode):
        return self.accounts[operation_mode]

    def snapshots_since(self, account_id, _start_date):
        return self.snapshots[account_id]

    def external_cash_flows(self, account_id, _started_at, _ended_before):
        return self.cash_flows[account_id]


class FakeAIClient:
    def __init__(self):
        self.context = None

    async def analyze(self, context):
        self.context = context
        return AIPortfolioComparisonResult(
            assessment="AI_AUTO",
            summary_focus="RETURN_GAP",
            key_point_focuses=["AI_AUTO_RETURN", "MY_INVESTMENT_RETURN"],
            caution_code="PAST_PERFORMANCE_AND_CASH_FLOW",
        )


def test_build_comparison_series_uses_only_common_dates_and_common_baseline() -> None:
    points = build_comparison_series(
        [
            snapshot(date(2026, 8, 20), "1000000"),
            snapshot(date(2026, 8, 21), "1050000"),
            snapshot(date(2026, 8, 22), "1100000"),
        ],
        [
            snapshot(date(2026, 8, 20), "2000000"),
            snapshot(date(2026, 8, 22), "2100000"),
        ],
    )

    assert [point.date for point in points] == [date(2026, 8, 20), date(2026, 8, 22)]
    assert points[-1].ai_auto_return_rate == Decimal("10.00")
    assert points[-1].my_investment_return_rate == Decimal("5.00")
    assert points[-1].return_rate_gap == Decimal("5.00")


def test_build_comparison_series_removes_mid_period_deposit_from_return() -> None:
    points = build_comparison_series(
        [
            snapshot(date(2026, 8, 20), "1000"),
            snapshot(date(2026, 8, 22), "1100"),
        ],
        [
            snapshot(date(2026, 8, 20), "1000"),
            snapshot(date(2026, 8, 22), "1600"),
        ],
        [],
        [cash_flow(date(2026, 8, 21), "500")],
    )

    assert points[-1].ai_auto_return_rate == Decimal("10.00")
    assert points[-1].my_investment_return_rate == Decimal("10.00")
    assert points[-1].return_rate_gap == Decimal("0.00")


def test_compare_service_does_not_treat_semi_auto_deposit_as_performance() -> None:
    auto_account = account("AUTO")
    my_account = account("SEMI_AUTO")
    service = PortfolioComparisonService(SimpleNamespace())
    service.repo = FakeRepository(
        auto_account,
        my_account,
        [
            snapshot(date(2026, 8, 20), "1000"),
            snapshot(date(2026, 8, 22), "1100"),
        ],
        [
            snapshot(date(2026, 8, 20), "1000"),
            snapshot(date(2026, 8, 22), "1600"),
        ],
        my_cash_flows=[cash_flow(date(2026, 8, 21), "500")],
    )

    result = asyncio.run(service.compare(7, "ALL"))

    assert result.accounts.ai_auto.return_rate == Decimal("10.00")
    assert result.accounts.my_investment.return_rate == Decimal("10.00")
    assert result.metrics.return_rate_gap == Decimal("0.00")
    assert result.metrics.leader == "TIE"


def test_compare_returns_server_metrics_and_frontend_ready_ai_analysis() -> None:
    auto_account = account("AUTO")
    my_account = account("SEMI_AUTO")
    client = FakeAIClient()
    service = PortfolioComparisonService(
        SimpleNamespace(),
        comparison_client=client,
        comparison_model_version="comparison-model-202608",
    )
    service.repo = FakeRepository(
        auto_account,
        my_account,
        [snapshot(date(2026, 8, 20), "1000000"), snapshot(date(2026, 8, 22), "1100000")],
        [snapshot(date(2026, 8, 20), "2000000"), snapshot(date(2026, 8, 22), "2100000")],
    )

    result = asyncio.run(service.compare(7, "ALL"))

    assert result.comparison_status == "AVAILABLE"
    assert result.metrics.return_rate_gap == Decimal("5.00")
    assert result.metrics.asset_gap == Decimal("-1000000.00")
    assert result.metrics.leader == "AI_AUTO"
    assert result.ai_analysis.status == "AVAILABLE"
    assert result.ai_analysis.model_version == "comparison-model-202608"
    assert "5.00%p" in result.ai_analysis.summary
    assert result.ai_analysis.key_points == [
        "AI 자동투자 기간수익률 +10.00%",
        "내 투자 기간수익률 +5.00%",
    ]
    assert client.context.observation_count == 2
    context_payload = client.context.model_dump(mode="json")
    assert "account_id" not in str(context_payload)
    assert "account_name" not in str(context_payload)


def test_compare_keeps_numeric_result_when_ai_is_not_connected() -> None:
    auto_account = account("AUTO")
    my_account = account("SEMI_AUTO")
    service = PortfolioComparisonService(SimpleNamespace())
    service.repo = FakeRepository(
        auto_account,
        my_account,
        [snapshot(date(2026, 8, 20), "100"), snapshot(date(2026, 8, 21), "101")],
        [snapshot(date(2026, 8, 20), "100"), snapshot(date(2026, 8, 21), "99")],
    )

    result = asyncio.run(service.compare(7, "ALL"))

    assert result.comparison_status == "AVAILABLE"
    assert result.metrics.return_rate_gap == Decimal("2.00")
    assert result.ai_analysis.status == "UNAVAILABLE"
    assert result.series


def test_compare_keeps_numeric_result_for_unexpected_ai_exception() -> None:
    class UnexpectedAIClient:
        async def analyze(self, _context):
            raise AttributeError("unexpected provider payload")

    auto_account = account("AUTO")
    my_account = account("SEMI_AUTO")
    service = PortfolioComparisonService(
        SimpleNamespace(),
        comparison_client=UnexpectedAIClient(),
    )
    service.repo = FakeRepository(
        auto_account,
        my_account,
        [snapshot(date(2026, 8, 20), "100"), snapshot(date(2026, 8, 21), "101")],
        [snapshot(date(2026, 8, 20), "100"), snapshot(date(2026, 8, 21), "99")],
    )

    result = asyncio.run(service.compare(7, "ALL"))

    assert result.comparison_status == "AVAILABLE"
    assert result.metrics.return_rate_gap == Decimal("2.00")
    assert result.ai_analysis.status == "UNAVAILABLE"


def test_compare_rejects_ai_assessment_that_disagrees_with_server_metrics() -> None:
    class MismatchedAIClient:
        async def analyze(self, _context):
            return AIPortfolioComparisonResult(
                assessment="MY_INVESTMENT",
                summary_focus="RETURN_GAP",
                key_point_focuses=["RETURN_GAP"],
                caution_code="PAST_PERFORMANCE_AND_CASH_FLOW",
            )

    auto_account = account("AUTO")
    my_account = account("SEMI_AUTO")
    service = PortfolioComparisonService(
        SimpleNamespace(),
        comparison_client=MismatchedAIClient(),
    )
    service.repo = FakeRepository(
        auto_account,
        my_account,
        [snapshot(date(2026, 8, 20), "100"), snapshot(date(2026, 8, 21), "102")],
        [snapshot(date(2026, 8, 20), "100"), snapshot(date(2026, 8, 21), "99")],
    )

    result = asyncio.run(service.compare(7, "ALL"))

    assert result.metrics.leader == "AI_AUTO"
    assert result.ai_analysis.status == "UNAVAILABLE"


def test_compare_requires_both_operation_mode_accounts() -> None:
    auto_account = account("AUTO")
    service = PortfolioComparisonService(SimpleNamespace())
    service.repo = FakeRepository(auto_account, None, [], [])

    with pytest.raises(ServiceError) as raised:
        asyncio.run(service.compare(7, "ALL"))

    assert raised.value.code == "COMPARISON_ACCOUNTS_REQUIRED"


def test_compare_reports_insufficient_common_snapshots_without_calling_ai() -> None:
    auto_account = account("AUTO")
    my_account = account("SEMI_AUTO")
    client = FakeAIClient()
    service = PortfolioComparisonService(SimpleNamespace(), comparison_client=client)
    service.repo = FakeRepository(
        auto_account,
        my_account,
        [snapshot(date(2026, 8, 20), "100")],
        [snapshot(date(2026, 8, 20), "100")],
    )

    result = asyncio.run(service.compare(7, "ALL"))

    assert result.comparison_status == "INSUFFICIENT_DATA"
    assert result.metrics is None
    assert result.series == []
    assert result.ai_analysis.status == "UNAVAILABLE"
    assert client.context is None
