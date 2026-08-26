"""AUTO와 SEMI_AUTO 계좌 비교 산식과 AI 부분 실패 경계를 검증한다."""

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.integrations.ai.portfolio_comparison_client import AIPortfolioComparisonResult
from app.services.portfolio_comparison import PortfolioComparisonService, build_comparison_series


def snapshot(observed_on: date, assets: str):
    return SimpleNamespace(snapshot_date=observed_on, total_assets=Decimal(assets))


def account(mode: str):
    return SimpleNamespace(
        id=uuid4(),
        account_name="AI 자동투자" if mode == "AUTO" else "내 투자",
        operation_mode=mode,
        selected_strategy_id="low" if mode == "AUTO" else "balanced",
    )


class FakeRepository:
    def __init__(self, auto_account, my_account, auto_snapshots, my_snapshots):
        self.accounts = {"AUTO": auto_account, "SEMI_AUTO": my_account}
        self.snapshots = {
            auto_account.id if auto_account else None: auto_snapshots,
            my_account.id if my_account else None: my_snapshots,
        }

    def account_for_user(self, _user_id, operation_mode):
        return self.accounts[operation_mode]

    def snapshots_since(self, account_id, _start_date):
        return self.snapshots[account_id]


class FakeAIClient:
    def __init__(self):
        self.context = None

    async def analyze(self, context):
        self.context = context
        return AIPortfolioComparisonResult(
            headline="AI 자동투자가 비교 기간에 앞섰습니다.",
            summary="공통 관측 기간의 수익률 격차는 5.00%p입니다.",
            key_points=["AI 자동투자 +10.00%", "내 투자 +5.00%"],
            caution="과거 가상투자 결과이며 미래 수익을 보장하지 않습니다.",
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
