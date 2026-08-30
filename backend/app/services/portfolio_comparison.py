"""AI 자동투자와 사용자 투자의 실제 일별 snapshot 성과를 비교한다."""

import logging
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.errors import ServiceError
from app.integrations.ai.portfolio_comparison_client import (
    AIPortfolioComparisonResult,
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


def _cash_flows_by_date(cash_flows: list) -> dict[date, Decimal]:
    result: dict[date, Decimal] = {}
    for cash_flow in cash_flows:
        recorded_at = cash_flow.created_at
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=KST)
        flow_date = recorded_at.astimezone(KST).date()
        result[flow_date] = result.get(flow_date, Decimal("0")) + cash_flow.amount
    return result


def _flows_between(
    cash_flows: dict[date, Decimal],
    previous_date: date,
    current_date: date,
) -> Decimal:
    return sum(
        (
            amount
            for flow_date, amount in cash_flows.items()
            if previous_date < flow_date <= current_date
        ),
        Decimal("0"),
    )


def build_comparison_series(
    auto_snapshots: list,
    my_snapshots: list,
    auto_cash_flows: list | None = None,
    my_cash_flows: list | None = None,
) -> list[PortfolioComparisonPointResponse]:
    """공통 관측일 사이 외부 현금흐름을 제거한 연결 TWR을 계산한다."""

    auto_by_date = {item.snapshot_date: item for item in auto_snapshots}
    my_by_date = {item.snapshot_date: item for item in my_snapshots}
    common_dates = sorted(auto_by_date.keys() & my_by_date.keys())
    if len(common_dates) < 2:
        return []

    auto_baseline = auto_by_date[common_dates[0]].total_assets
    my_baseline = my_by_date[common_dates[0]].total_assets
    if auto_baseline <= 0 or my_baseline <= 0:
        return []

    auto_flows_by_date = _cash_flows_by_date(auto_cash_flows or [])
    my_flows_by_date = _cash_flows_by_date(my_cash_flows or [])
    auto_growth = Decimal("1")
    my_growth = Decimal("1")
    result: list[PortfolioComparisonPointResponse] = []
    for index, observed_on in enumerate(common_dates):
        if index > 0:
            previous_on = common_dates[index - 1]
            previous_auto_assets = auto_by_date[previous_on].total_assets
            previous_my_assets = my_by_date[previous_on].total_assets
            if previous_auto_assets <= 0 or previous_my_assets <= 0:
                return []
            auto_external_flow = _flows_between(
                auto_flows_by_date,
                previous_on,
                observed_on,
            )
            my_external_flow = _flows_between(
                my_flows_by_date,
                previous_on,
                observed_on,
            )
            auto_growth *= (
                auto_by_date[observed_on].total_assets - auto_external_flow
            ) / previous_auto_assets
            my_growth *= (
                my_by_date[observed_on].total_assets - my_external_flow
            ) / previous_my_assets
        auto_rate = ((auto_growth - 1) * 100).quantize(RATE_SCALE)
        my_rate = ((my_growth - 1) * 100).quantize(RATE_SCALE)
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
            analysis = self._render_ai_analysis(result, response)
        except ServiceError as exc:
            if not exc.code.startswith("AI_"):
                raise
            logger.warning("AI portfolio comparison unavailable code=%s", exc.code)
            return response.model_copy(update={
                "ai_analysis": self._unavailable_analysis("AI 비교 분석을 현재 불러올 수 없습니다."),
            })
        except Exception:
            logger.exception("Unexpected AI portfolio comparison failure")
            return response.model_copy(update={
                "ai_analysis": self._unavailable_analysis("AI 비교 분석을 현재 불러올 수 없습니다."),
            })

        return response.model_copy(update={
            "ai_analysis": analysis,
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
        common_dates = sorted(
            {item.snapshot_date for item in auto_snapshots}
            & {item.snapshot_date for item in my_snapshots}
        )
        common_observation_count = len(common_dates)
        auto_cash_flows = []
        my_cash_flows = []
        if len(common_dates) >= 2:
            cash_flow_started_at = datetime.combine(
                common_dates[0] + timedelta(days=1),
                time.min,
                KST,
            )
            cash_flow_ended_before = datetime.combine(
                common_dates[-1] + timedelta(days=1),
                time.min,
                KST,
            )
            auto_cash_flows = self.repo.external_cash_flows(
                auto_account.id,
                cash_flow_started_at,
                cash_flow_ended_before,
            )
            my_cash_flows = self.repo.external_cash_flows(
                my_account.id,
                cash_flow_started_at,
                cash_flow_ended_before,
            )
        series = build_comparison_series(
            auto_snapshots,
            my_snapshots,
            auto_cash_flows,
            my_cash_flows,
        )

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

    def _render_ai_analysis(
        self,
        result: AIPortfolioComparisonResult,
        response: PortfolioComparisonResponse,
    ) -> PortfolioComparisonAIAnalysisResponse:
        metrics = response.metrics
        if metrics is None or result.assessment != metrics.leader:
            raise ServiceError(
                "AI_INVALID_COMPARISON_RESPONSE",
                "투자 비교 분석이 서버 계산 결과와 일치하지 않습니다.",
                502,
            )

        auto = response.accounts.ai_auto
        mine = response.accounts.my_investment
        if auto.return_rate is None or mine.return_rate is None:
            raise ServiceError(
                "AI_INVALID_COMPARISON_RESPONSE",
                "투자 비교 분석에 필요한 서버 계산값이 없습니다.",
                502,
            )

        leader_labels = {
            "AI_AUTO": "AI 자동투자",
            "MY_INVESTMENT": "내 투자",
        }
        if metrics.leader == "TIE":
            headline = "두 투자 방식의 비교 기간 수익률이 같습니다."
        else:
            headline = f"{leader_labels[metrics.leader]}가 비교 기간 수익률에서 앞섰습니다."

        if result.summary_focus == "ACCOUNT_RETURNS":
            summary = (
                f"AI 자동투자 수익률은 {auto.return_rate:+.2f}%, "
                f"내 투자 수익률은 {mine.return_rate:+.2f}%입니다."
            )
        elif metrics.leader == "TIE":
            summary = "공통 관측 기간의 수익률 격차는 0.00%p입니다."
        else:
            summary = (
                f"공통 관측 기간의 수익률 격차는 "
                f"{abs(metrics.return_rate_gap):.2f}%p이며 "
                f"{leader_labels[metrics.leader]}가 앞섰습니다."
            )

        key_point_templates = {
            "AI_AUTO_RETURN": f"AI 자동투자 기간수익률 {auto.return_rate:+.2f}%",
            "MY_INVESTMENT_RETURN": f"내 투자 기간수익률 {mine.return_rate:+.2f}%",
            "RETURN_GAP": f"수익률 격차 {abs(metrics.return_rate_gap):.2f}%p",
            "OBSERVATION_COUNT": f"공통 장마감 관측 {response.observation_count}개",
            "ASSET_GAP": (
                f"원화 자산 차이(AI-내 투자) {metrics.asset_gap:+,.2f}원"
            ),
        }
        return PortfolioComparisonAIAnalysisResponse(
            status="AVAILABLE",
            headline=headline,
            summary=summary,
            key_points=[key_point_templates[focus] for focus in result.key_point_focuses],
            caution=(
                "수익률은 외부 현금흐름을 조정한 과거 가상투자 결과이며 "
                "미래 수익을 보장하지 않습니다. 원화 자산 차이는 초기 자산 규모의 "
                "영향을 받을 수 있습니다."
            ),
            model_version=self.comparison_model_version,
            generated_at=datetime.now(UTC),
        )

    @staticmethod
    def _unavailable_analysis(message: str) -> PortfolioComparisonAIAnalysisResponse:
        return PortfolioComparisonAIAnalysisResponse(
            status="UNAVAILABLE",
            summary=message,
        )
