"""AI 자동투자와 사용자 투자의 실제 일별 snapshot 성과를 비교한다."""

import logging
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.errors import ServiceError
from app.integrations.ai.portfolio_comparison_client import (
    PortfolioComparisonAIClient,
    PortfolioComparisonAnalysisContext,
)
from app.repositories import TradingRepository
from app.schemas.api import (
    PortfolioComparisonAIAnalysisResponse,
    PortfolioComparisonAccountResponse,
    PortfolioComparisonAccountsResponse,
    PortfolioComparisonMetricsResponse,
    PortfolioComparisonPointResponse,
    PortfolioComparisonResponse,
)


HISTORY_DAYS = {"1M": 31, "3M": 93, "1Y": 366}
KST = timezone(timedelta(hours=9))
RATE_SCALE = Decimal("0.01")
MONEY_SCALE = Decimal("0.01")
logger = logging.getLogger(__name__)


def _return_rate(current: Decimal, baseline: Decimal) -> Decimal:
    return ((current / baseline - 1) * 100).quantize(RATE_SCALE)


def build_comparison_series(
    auto_snapshots: list,
    my_snapshots: list,
) -> list[PortfolioComparisonPointResponse]:
    """두 계좌에 모두 존재하는 실제 관측일만 같은 기준일로 정규화한다."""

    auto_by_date = {item.snapshot_date: item for item in auto_snapshots}
    my_by_date = {item.snapshot_date: item for item in my_snapshots}
    common_dates = sorted(auto_by_date.keys() & my_by_date.keys())
    if len(common_dates) < 2:
        return []

    auto_baseline = auto_by_date[common_dates[0]].total_assets
    my_baseline = my_by_date[common_dates[0]].total_assets
    if auto_baseline <= 0 or my_baseline <= 0:
        return []

    result: list[PortfolioComparisonPointResponse] = []
    for observed_on in common_dates:
        auto_rate = _return_rate(auto_by_date[observed_on].total_assets, auto_baseline)
        my_rate = _return_rate(my_by_date[observed_on].total_assets, my_baseline)
        result.append(PortfolioComparisonPointResponse(
            date=observed_on,
            ai_auto_return_rate=auto_rate,
            my_investment_return_rate=my_rate,
            return_rate_gap=(auto_rate - my_rate).quantize(RATE_SCALE),
        ))
    return result


class PortfolioComparisonService:
    def __init__(
        self,
        session: Session,
        comparison_client: PortfolioComparisonAIClient | None = None,
        *,
        comparison_model_version: str = "portfolio-comparison-v1",
    ) -> None:
        self.repo = TradingRepository(session)
        self.comparison_client = comparison_client
        self.comparison_model_version = comparison_model_version

    async def compare(self, user_id: int, period: str) -> PortfolioComparisonResponse:
        response, context = await run_in_threadpool(self._prepare, user_id, period)
        if context is None:
            return response
        if self.comparison_client is None:
            return response.model_copy(update={
                "ai_analysis": self._unavailable_analysis("AI 비교 분석 모델 연결을 준비 중입니다."),
            })

        try:
            result = await self.comparison_client.analyze(context)
        except ServiceError as exc:
            if not exc.code.startswith("AI_"):
                raise
            logger.warning("AI portfolio comparison unavailable code=%s", exc.code)
            return response.model_copy(update={
                "ai_analysis": self._unavailable_analysis("AI 비교 분석을 현재 불러올 수 없습니다."),
            })

        return response.model_copy(update={
            "ai_analysis": PortfolioComparisonAIAnalysisResponse(
                status="AVAILABLE",
                headline=result.headline,
                summary=result.summary,
                key_points=result.key_points,
                caution=result.caution,
                model_version=self.comparison_model_version,
                generated_at=datetime.now(UTC),
            ),
        })

    def _prepare(
        self,
        user_id: int,
        period: str,
    ) -> tuple[PortfolioComparisonResponse, PortfolioComparisonAnalysisContext | None]:
        auto_account = self.repo.account_for_user(user_id, "AUTO")
        my_account = self.repo.account_for_user(user_id, "SEMI_AUTO")
        missing = [
            label
            for account, label in ((auto_account, "AUTO"), (my_account, "SEMI_AUTO"))
            if account is None
        ]
        if missing:
            raise ServiceError(
                "COMPARISON_ACCOUNTS_REQUIRED",
                f"투자 비교를 위해 {', '.join(missing)} 계좌가 필요합니다.",
                409,
            )

        start_date = None
        if period != "ALL":
            start_date = datetime.now(KST).date() - timedelta(days=HISTORY_DAYS[period])
        auto_snapshots = self.repo.snapshots_since(auto_account.id, start_date)
        my_snapshots = self.repo.snapshots_since(my_account.id, start_date)
        common_observation_count = len(
            {item.snapshot_date for item in auto_snapshots}
            & {item.snapshot_date for item in my_snapshots}
        )
        series = build_comparison_series(auto_snapshots, my_snapshots)

        if not series:
            response = PortfolioComparisonResponse(
                comparison_status="INSUFFICIENT_DATA",
                period=period,
                baseline_date=None,
                as_of=None,
                observation_count=common_observation_count,
                accounts=PortfolioComparisonAccountsResponse(
                    ai_auto=self._account_summary(auto_account, auto_snapshots),
                    my_investment=self._account_summary(my_account, my_snapshots),
                ),
                metrics=None,
                series=[],
                ai_analysis=self._unavailable_analysis(
                    "두 계좌의 공통 일별 자산 기록이 2개 이상 쌓이면 "
                    "AI 비교 분석을 제공합니다."
                ),
            )
            return response, None

        auto_by_date = {item.snapshot_date: item for item in auto_snapshots}
        my_by_date = {item.snapshot_date: item for item in my_snapshots}
        baseline_date = series[0].date
        as_of = series[-1].date
        auto_baseline = auto_by_date[baseline_date].total_assets.quantize(MONEY_SCALE)
        auto_current = auto_by_date[as_of].total_assets.quantize(MONEY_SCALE)
        my_baseline = my_by_date[baseline_date].total_assets.quantize(MONEY_SCALE)
        my_current = my_by_date[as_of].total_assets.quantize(MONEY_SCALE)
        auto_return = series[-1].ai_auto_return_rate
        my_return = series[-1].my_investment_return_rate
        return_gap = (auto_return - my_return).quantize(RATE_SCALE)
        asset_gap = (auto_current - my_current).quantize(MONEY_SCALE)
        leader = "AI_AUTO" if return_gap > 0 else "MY_INVESTMENT" if return_gap < 0 else "TIE"

        accounts = PortfolioComparisonAccountsResponse(
            ai_auto=PortfolioComparisonAccountResponse(
                account_id=auto_account.id,
                account_name=auto_account.account_name,
                operation_mode="AUTO",
                strategy_id=auto_account.selected_strategy_id,
                baseline_assets=auto_baseline,
                current_assets=auto_current,
                return_rate=auto_return,
            ),
            my_investment=PortfolioComparisonAccountResponse(
                account_id=my_account.id,
                account_name=my_account.account_name,
                operation_mode="SEMI_AUTO",
                strategy_id=my_account.selected_strategy_id,
                baseline_assets=my_baseline,
                current_assets=my_current,
                return_rate=my_return,
            ),
        )
        metrics = PortfolioComparisonMetricsResponse(
            return_rate_gap=return_gap,
            asset_gap=asset_gap,
            leader=leader,
        )
        response = PortfolioComparisonResponse(
            comparison_status="AVAILABLE",
            period=period,
            baseline_date=baseline_date,
            as_of=as_of,
            observation_count=len(series),
            accounts=accounts,
            metrics=metrics,
            series=series,
            ai_analysis=self._unavailable_analysis("AI 비교 분석 모델 연결을 준비 중입니다."),
        )
        context = PortfolioComparisonAnalysisContext(
            period=period,
            baseline_date=baseline_date,
            as_of=as_of,
            observation_count=len(series),
            ai_auto={
                "operation_mode": "AUTO",
                "strategy_id": auto_account.selected_strategy_id,
                "baseline_assets": auto_baseline,
                "current_assets": auto_current,
                "return_rate": auto_return,
            },
            my_investment={
                "operation_mode": "SEMI_AUTO",
                "strategy_id": my_account.selected_strategy_id,
                "baseline_assets": my_baseline,
                "current_assets": my_current,
                "return_rate": my_return,
            },
            return_rate_gap=return_gap,
            asset_gap=asset_gap,
            leader=leader,
        )
        return response, context

    @staticmethod
    def _account_summary(account, snapshots: list) -> PortfolioComparisonAccountResponse:
        latest = snapshots[-1] if snapshots else None
        return PortfolioComparisonAccountResponse(
            account_id=account.id,
            account_name=account.account_name,
            operation_mode=account.operation_mode,
            strategy_id=account.selected_strategy_id,
            baseline_assets=None,
            current_assets=latest.total_assets.quantize(MONEY_SCALE) if latest else None,
            return_rate=None,
        )

    @staticmethod
    def _unavailable_analysis(message: str) -> PortfolioComparisonAIAnalysisResponse:
        return PortfolioComparisonAIAnalysisResponse(
            status="UNAVAILABLE",
            summary=message,
        )
