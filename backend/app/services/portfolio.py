"""실제 계좌·시세·KRX metadata를 결합해 포트폴리오 분석을 제공한다."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceError
from app.integrations.ai.rebalancing_client import (
    AIRebalancingResult,
    RebalancingAIClient,
    RebalancingAnalysisContext,
)
from app.integrations.kis.models import CurrentQuote
from app.repositories import TradingRepository
from app.repositories.market_data import MarketDataRepository
from app.schemas.api import (
    PortfolioAllocationResponse,
    PortfolioContributionResponse,
    PortfolioHomeAccountResponse,
    PortfolioHomeResponse,
    PortfolioHomeSummaryResponse,
    PortfolioHistoryPointResponse,
    PortfolioHistoryResponse,
    PortfolioResponse,
    PositionResponse,
    RebalancingInsightResponse,
    RebalancingProposalResponse,
)
from app.services.market import MarketService

HISTORY_DAYS = {"1M": 31, "3M": 93, "1Y": 366}
KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PortfolioHomeData:
    account: PortfolioHomeAccountResponse
    portfolio: PortfolioResponse
    history: PortfolioHistoryResponse
    positions: list[PositionResponse]
    allocations: list[PortfolioAllocationResponse]
    valuation_as_of: datetime | None
    price_sources: list[str]


def calculate_return(profit: Decimal, purchase: Decimal) -> Decimal:
    return (
        Decimal("0")
        if purchase == 0
        else (profit / purchase * 100).quantize(Decimal("0.01"))
    )


def calculate_weight(evaluation: Decimal, total_assets: Decimal) -> Decimal:
    return (
        Decimal("0")
        if total_assets == 0
        else (evaluation / total_assets * 100).quantize(Decimal("0.01"))
    )


def calculate_rebalancing(
    total_assets: Decimal,
    current_weights: dict[str, Decimal],
    target_weights: dict[str, Decimal],
    stock_names: dict[str, str | None],
) -> list[RebalancingProposalResponse]:
    """명시적으로 저장된 목표 비중만 사용해 금액 기준 조정안을 계산한다."""

    if not target_weights:
        return []
    proposals: list[RebalancingProposalResponse] = []
    for stock_code in sorted(set(current_weights) | set(target_weights)):
        current = current_weights.get(stock_code, Decimal("0"))
        target = (target_weights.get(stock_code, Decimal("0")) * 100).quantize(
            Decimal("0.01")
        )
        diff = (current - target).quantize(Decimal("0.01"))
        if diff == 0:
            continue
        proposals.append(
            RebalancingProposalResponse(
                stock_code=stock_code,
                stock_name=stock_names.get(stock_code),
                current_weight=current,
                target_weight=target,
                weight_diff=diff,
                action="SELL" if diff > 0 else "BUY",
                recommended_amount=(total_assets * abs(diff) / 100).quantize(
                    Decimal("0.01")
                ),
            )
        )
    return sorted(proposals, key=lambda item: item.recommended_amount, reverse=True)


def validate_target_weights(
    target_weights: dict[str, Decimal],
    *,
    allow_cash_buffer: bool = False,
) -> None:
    total = sum(target_weights.values(), Decimal("0"))
    if not target_weights:
        return
    valid_total = (
        total == Decimal("0.95") if allow_cash_buffer else total == Decimal("1")
    )
    if not valid_total:
        message = (
            "현금 버퍼를 사용하는 전략의 주식 목표 비중 합계는 0.95여야 합니다."
            if allow_cash_buffer
            else "전략 목표 비중 합계가 1이 아닙니다."
        )
        raise ServiceError("INVALID_STRATEGY_TARGET_WEIGHTS", message, 503)


def build_history_points(
    snapshots: list, indices: list
) -> list[PortfolioHistoryPointResponse]:
    """실제 snapshot 날짜에 맞춰 포트폴리오와 직전 KOSPI 수익률을 정규화한다."""

    if not snapshots:
        return []
    snapshots = sorted(snapshots, key=lambda item: item.snapshot_date)
    unique_indices = {item.trade_date: item for item in indices}
    indices = [unique_indices[trade_date] for trade_date in sorted(unique_indices)]
    first_assets = snapshots[0].total_assets
    benchmark_base: Decimal | None = None
    latest_benchmark: Decimal | None = None
    index_position = 0
    items: list[PortfolioHistoryPointResponse] = []
    for snapshot_index, snapshot in enumerate(snapshots):
        while (
            index_position < len(indices)
            and indices[index_position].trade_date <= snapshot.snapshot_date
        ):
            latest_benchmark = indices[index_position].close_value
            index_position += 1
        if snapshot_index == 0:
            benchmark_base = latest_benchmark
        portfolio_rate = (
            ((snapshot.total_assets / first_assets) - 1) * 100
            if first_assets and first_assets > 0
            else Decimal("0")
        )
        benchmark_rate = (
            ((latest_benchmark / benchmark_base) - 1) * 100
            if latest_benchmark is not None and benchmark_base
            else None
        )
        items.append(
            PortfolioHistoryPointResponse(
                date=snapshot.snapshot_date,
                total_assets=snapshot.total_assets,
                portfolio_return_rate=portfolio_rate.quantize(Decimal("0.01")),
                benchmark_return_rate=(
                    benchmark_rate.quantize(Decimal("0.01"))
                    if benchmark_rate is not None
                    else None
                ),
            )
        )
    return items


def sort_positions(
    positions: list[PositionResponse],
    sort_by: str,
    order: str,
) -> list[PositionResponse]:
    """허용된 포트폴리오 컬럼으로 보유종목을 결정적으로 정렬한다."""

    if sort_by == "stock_name":
        key = lambda item: (
            (item.stock_name or item.stock_code).casefold(),
            item.stock_code,
        )
    else:
        key = lambda item: (getattr(item, sort_by), item.stock_code)
    return sorted(positions, key=key, reverse=order == "desc")


def build_allocations(
    portfolio: PortfolioResponse,
) -> list[PortfolioAllocationResponse]:
    """도넛 차트 합계가 전체 자산을 나타내도록 보유종목과 현금을 함께 반환한다."""

    allocations = [
        PortfolioAllocationResponse(
            type="STOCK",
            stock_code=position.stock_code,
            name=position.stock_name or position.stock_code,
            amount=position.evaluation_amount,
            weight=position.weight,
        )
        for position in portfolio.positions
    ]
    allocations.append(
        PortfolioAllocationResponse(
            type="CASH",
            stock_code=None,
            name="현금",
            amount=portfolio.cash_balance,
            weight=calculate_weight(portfolio.cash_balance, portfolio.total_assets),
        )
    )
    return allocations


class PortfolioService:
    def __init__(
        self,
        session: Session,
        market: MarketService | None = None,
        rebalancing_client: RebalancingAIClient | None = None,
        *,
        rebalancing_model_version: str = "rebalancing-v1",
    ) -> None:
        self.session = session
        self.repo = TradingRepository(session)
        self.market_repo = MarketDataRepository(session)
        self.market = market
        self.rebalancing_client = rebalancing_client
        self.rebalancing_model_version = rebalancing_model_version

    def evaluate(self, user_id: int, account_id: UUID) -> PortfolioResponse:
        account = self.repo.owned_account(account_id, user_id)
        if not account:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")

        return self._evaluate_account(account)

    async def home(
        self,
        user_id: int,
        account_id: UUID,
        period: str,
        sort_by: str,
        order: str,
    ) -> PortfolioHomeResponse:
        """홈 화면에 필요한 실제 계좌 평가와 기간 이력을 한 번에 조합한다."""

        data = await run_in_threadpool(
            self._prepare_home,
            user_id,
            account_id,
            period,
            sort_by,
            order,
        )
        insight, proposals = await self._ai_rebalancing(
            data.account,
            data.portfolio,
            valuation_as_of=data.valuation_as_of,
        )
        return PortfolioHomeResponse(
            account=data.account,
            summary=PortfolioHomeSummaryResponse(
                cash_balance=data.portfolio.cash_balance,
                total_purchase_amount=data.portfolio.total_purchase_amount,
                total_evaluation_amount=data.portfolio.total_evaluation_amount,
                total_assets=data.portfolio.total_assets,
                unrealized_profit=data.portfolio.unrealized_profit,
                realized_profit=data.portfolio.realized_profit,
                return_rate=data.portfolio.return_rate,
                today_profit=data.portfolio.today_profit,
                top_contributor=data.portfolio.top_contributor,
                invested_principal=data.portfolio.invested_principal,
                valuation_profit=data.portfolio.valuation_profit,
                withdrawable_amount=data.portfolio.withdrawable_amount,
            ),
            trend=data.history,
            allocations=data.allocations,
            positions=data.positions,
            contributions=data.portfolio.contributions,
            strategy_targets_available=data.portfolio.strategy_targets_available,
            rebalancing_insight=insight,
            rebalancing_proposals=proposals,
            valuation_as_of=data.valuation_as_of,
            price_sources=data.price_sources,
        )

    def _prepare_home(
        self,
        user_id: int,
        account_id: UUID,
        period: str,
        sort_by: str,
        order: str,
    ) -> PortfolioHomeData:
        """DB·Redis/KIS 조회와 포트폴리오 계산을 동기 worker에서 완료한다."""

        account = self.repo.owned_account(account_id, user_id)
        if not account:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")

        portfolio = self._evaluate_account(account)
        history = self._history_response(account.id, period)
        positions = sort_positions(portfolio.positions, sort_by, order)
        valuation_as_of = max(
            (position.price_as_of for position in portfolio.positions),
            default=None,
        )
        return PortfolioHomeData(
            account=PortfolioHomeAccountResponse(
                id=account.id,
                account_name=account.account_name,
                operation_mode=account.operation_mode,
                status=account.status,
                selected_strategy_id=account.selected_strategy_id,
            ),
            portfolio=portfolio,
            history=history,
            positions=positions,
            allocations=build_allocations(portfolio),
            valuation_as_of=valuation_as_of,
            price_sources=sorted(
                {position.price_source for position in portfolio.positions}
            ),
        )

    async def _ai_rebalancing(
        self,
        account,
        portfolio: PortfolioResponse,
        *,
        valuation_as_of: datetime | None,
    ) -> tuple[RebalancingInsightResponse, list[RebalancingProposalResponse]]:
        candidates = portfolio.rebalancing_proposals
        if not portfolio.strategy_targets_available:
            return (
                self._rebalancing_unavailable("적용 가능한 전략 목표 비중이 없습니다."),
                [],
            )
        if not candidates:
            return (
                RebalancingInsightResponse(
                    status="NOT_NEEDED",
                    summary="현재 비중이 전략 목표 비중과 일치해 리밸런싱 제안이 없습니다.",
                    model_version=None,
                    generated_at=None,
                ),
                [],
            )
        if self.rebalancing_client is None:
            return (
                self._rebalancing_unavailable(
                    "리밸런싱 제안 모델 연결을 준비 중입니다."
                ),
                [],
            )

        context = RebalancingAnalysisContext(
            operation_mode=account.operation_mode,
            strategy_id=account.selected_strategy_id,
            total_assets=portfolio.total_assets,
            cash_balance=portfolio.cash_balance,
            valuation_as_of=valuation_as_of,
            validated_candidates=[
                {
                    "stock_code": candidate.stock_code,
                    "stock_name": candidate.stock_name,
                    "current_weight": candidate.current_weight,
                    "target_weight": candidate.target_weight,
                    "weight_diff": candidate.weight_diff,
                    "action": candidate.action,
                    "recommended_amount": candidate.recommended_amount,
                }
                for candidate in candidates
            ],
        )
        try:
            result = await self.rebalancing_client.analyze(context)
            proposals = self._validated_ai_proposals(result, candidates)
        except ServiceError as exc:
            if not exc.code.startswith("AI_"):
                raise
            logger.warning("AI rebalancing unavailable code=%s", exc.code)
            return (
                self._rebalancing_unavailable(
                    "AI 리밸런싱 제안을 현재 불러올 수 없습니다."
                ),
                [],
            )

        return (
            RebalancingInsightResponse(
                status="AVAILABLE",
                summary=result.summary,
                model_version=self.rebalancing_model_version,
                generated_at=datetime.now(UTC),
            ),
            proposals,
        )

    @staticmethod
    def _validated_ai_proposals(
        result: AIRebalancingResult,
        candidates: list[RebalancingProposalResponse],
    ) -> list[RebalancingProposalResponse]:
        candidate_by_code = {
            candidate.stock_code: candidate for candidate in candidates
        }
        proposals = sorted(result.proposals, key=lambda item: item.priority)
        codes = [item.stock_code for item in proposals]
        priorities = [item.priority for item in proposals]
        if len(set(codes)) != len(codes) or priorities != list(
            range(1, len(proposals) + 1)
        ):
            raise ServiceError(
                "AI_INVALID_REBALANCING_RESPONSE",
                "AI 리밸런싱 제안 순서가 올바르지 않습니다.",
                502,
            )

        validated: list[RebalancingProposalResponse] = []
        for item in proposals:
            candidate = candidate_by_code.get(item.stock_code)
            if candidate is None or any(
                (
                    item.current_weight != candidate.current_weight,
                    item.target_weight != candidate.target_weight,
                    item.weight_diff != candidate.weight_diff,
                    item.action != candidate.action,
                    item.recommended_amount != candidate.recommended_amount,
                )
            ):
                raise ServiceError(
                    "AI_INVALID_REBALANCING_RESPONSE",
                    "AI 리밸런싱 제안이 검증된 포트폴리오 후보와 일치하지 않습니다.",
                    502,
                )
            validated.append(
                candidate.model_copy(
                    update={
                        "priority": item.priority,
                        "reason": item.reason,
                        "why_now": item.why_now,
                        "source": "AI",
                    }
                )
            )
        return validated

    @staticmethod
    def _rebalancing_unavailable(message: str) -> RebalancingInsightResponse:
        return RebalancingInsightResponse(
            status="UNAVAILABLE",
            summary=message,
            model_version=None,
            generated_at=None,
        )

    def _evaluate_account(
        self,
        account,
        *,
        quote_provider: Callable[[str], CurrentQuote] | None = None,
        effective_on: date | None = None,
        include_strategy: bool = True,
    ) -> PortfolioResponse:
        account_id = account.id
        effective_on = effective_on or datetime.now(KST).date()
        if quote_provider is None:
            if self.market is None:
                self.market = MarketService()
            quote_provider = self._current_quote

        evaluated: list[dict] = []
        purchase_total = Decimal("0")
        evaluation_total = Decimal("0")
        realized_total = Decimal("0")
        for position in self.repo.positions(account_id):
            realized_total += position.realized_profit
            if position.quantity == 0:
                continue
            quote = quote_provider(position.stock_code)
            stock = self.market_repo.stock(position.stock_code)
            purchase = (position.average_price * position.quantity).quantize(
                Decimal("0.01")
            )
            evaluation = (quote.price * position.quantity).quantize(Decimal("0.01"))
            profit = evaluation - purchase
            today_profit = (
                ((quote.price - quote.previous_close) * position.quantity).quantize(
                    Decimal("0.01")
                )
                if quote.previous_close is not None
                else None
            )
            purchase_total += purchase
            evaluation_total += evaluation
            evaluated.append(
                {
                    "position": position,
                    "quote": quote,
                    "stock": stock,
                    "purchase": purchase,
                    "evaluation": evaluation,
                    "profit": profit,
                    "today_profit": today_profit,
                }
            )

        total_assets = (account.cash_balance + evaluation_total).quantize(
            Decimal("0.01")
        )
        principal_value = getattr(account, "invested_principal", None)
        if principal_value is None:
            principal_value = getattr(account, "initial_cash", Decimal("0"))
        invested_principal = Decimal(principal_value).quantize(Decimal("0.01"))
        valuation_profit = (total_assets - invested_principal).quantize(
            Decimal("0.01")
        )
        withdrawable_amount = (
            Decimal(account.cash_balance)
            + sum(
                (
                    item["evaluation"]
                    for item in evaluated
                    if item["evaluation"] >= Decimal("1")
                ),
                Decimal("0"),
            )
        ).quantize(Decimal("0.01"))
        unrealized = evaluation_total - purchase_total
        rows: list[PositionResponse] = []
        current_weights: dict[str, Decimal] = {}
        stock_names: dict[str, str | None] = {}
        contributions: list[PortfolioContributionResponse] = []
        all_today_prices_available = bool(evaluated) and all(
            item["today_profit"] is not None for item in evaluated
        )
        today_profit = (
            sum((item["today_profit"] for item in evaluated), Decimal("0"))
            if all_today_prices_available
            else None
        )

        for item in evaluated:
            position = item["position"]
            quote = item["quote"]
            stock = item["stock"]
            weight = calculate_weight(item["evaluation"], total_assets)
            stock_name = stock.stock_name if stock else None
            current_weights[position.stock_code] = weight
            stock_names[position.stock_code] = stock_name
            rows.append(
                PositionResponse(
                    stock_code=position.stock_code,
                    stock_name=stock_name,
                    sector=stock.sector if stock else None,
                    quantity=position.quantity,
                    average_price=position.average_price,
                    current_price=quote.price,
                    previous_close=quote.previous_close,
                    change_rate=quote.change_rate,
                    purchase_amount=item["purchase"],
                    evaluation_amount=item["evaluation"],
                    unrealized_profit=item["profit"],
                    return_rate=calculate_return(item["profit"], item["purchase"]),
                    realized_profit=position.realized_profit,
                    weight=weight,
                    today_profit=item["today_profit"],
                    price_source=quote.source,
                    price_as_of=quote.as_of,
                )
            )
            if item["today_profit"] is not None:
                share = (
                    (item["today_profit"] / today_profit * 100).quantize(
                        Decimal("0.01")
                    )
                    if all_today_prices_available and today_profit != Decimal("0")
                    else None
                )
                contributions.append(
                    PortfolioContributionResponse(
                        stock_code=position.stock_code,
                        stock_name=stock_name,
                        amount=item["today_profit"],
                        share_rate=share,
                    )
                )
        contributions.sort(key=lambda item: item.amount, reverse=True)

        targets = (
            self.repo.target_weights(account.selected_strategy_id, effective_on)
            if include_strategy and account.selected_strategy_id
            else {}
        )
        validate_target_weights(
            targets,
            allow_cash_buffer=account.selected_strategy_id == "momentum",
        )
        for stock_code in targets:
            if stock_code not in stock_names:
                stock = self.market_repo.stock(stock_code)
                stock_names[stock_code] = stock.stock_name if stock else None
        proposals = (
            calculate_rebalancing(total_assets, current_weights, targets, stock_names)
            if targets
            else []
        )

        return PortfolioResponse(
            account_id=account.id,
            cash_balance=account.cash_balance,
            total_purchase_amount=purchase_total,
            total_evaluation_amount=evaluation_total,
            total_assets=total_assets,
            unrealized_profit=unrealized,
            realized_profit=realized_total,
            return_rate=calculate_return(valuation_profit, invested_principal),
            today_profit=today_profit,
            top_contributor=contributions[0] if contributions else None,
            contributions=contributions,
            strategy_targets_available=bool(targets),
            rebalancing_proposals=proposals,
            positions=rows,
            invested_principal=invested_principal,
            valuation_profit=valuation_profit,
            withdrawable_amount=withdrawable_amount,
        )

    def _current_quote(self, stock_code: str) -> CurrentQuote:
        """KIS 현재가 장애 시 DB에 적재된 최신 KRX 종가로 평가를 계속한다."""

        try:
            return self.market.get_quote(stock_code)
        except ServiceError as exc:
            latest = self.market_repo.latest_price(stock_code)
            if latest is None:
                raise
            logger.warning(
                "Live quote unavailable; using latest KRX close stock_code=%s code=%s trade_date=%s",
                stock_code,
                exc.code,
                latest.trade_date,
            )
            return self._closing_quote(stock_code, latest.trade_date)

    def capture_daily_snapshots(self, snapshot_date: date | None = None) -> int:
        """활성 계좌를 평가해 장 마감 후 일별 스냅샷으로 저장한다."""

        snapshot_date = snapshot_date or datetime.now(KST).date()
        if not self.market_repo.has_kospi_close(snapshot_date):
            return 0
        captured = 0
        try:
            for account in self.repo.active_accounts():
                response = self._evaluate_account(
                    account,
                    quote_provider=lambda stock_code: self._closing_quote(
                        stock_code, snapshot_date
                    ),
                    effective_on=snapshot_date,
                    include_strategy=False,
                )
                self.repo.save_snapshot(
                    account.id,
                    snapshot_date,
                    cash_balance=response.cash_balance,
                    total_purchase_amount=response.total_purchase_amount,
                    total_evaluation_amount=response.total_evaluation_amount,
                    total_assets=response.total_assets,
                    unrealized_profit=response.unrealized_profit,
                    realized_profit=response.realized_profit,
                    return_rate=response.return_rate,
                )
                captured += 1
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return captured

    def _closing_quote(self, stock_code: str, snapshot_date: date) -> CurrentQuote:
        prices = self.market_repo.closing_prices(stock_code, snapshot_date)
        if not prices or prices[0].trade_date != snapshot_date:
            raise ServiceError(
                "MARKET_CLOSE_UNAVAILABLE",
                f"{stock_code} 종목의 장 마감 가격을 찾을 수 없습니다.",
                503,
            )
        latest = prices[0]
        previous_close = prices[1].close_price if len(prices) > 1 else None
        return CurrentQuote(
            stock_code=stock_code,
            price=latest.close_price,
            previous_close=previous_close,
            change_amount=latest.change_amount,
            change_rate=latest.change_rate,
            volume=latest.volume,
            as_of=datetime.combine(latest.trade_date, time(15, 30), tzinfo=KST),
            source=latest.source,
        )

    def history(
        self, user_id: int, account_id: UUID, period: str
    ) -> PortfolioHistoryResponse:
        account = self.repo.owned_account(account_id, user_id)
        if not account:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        return self._history_response(account.id, period)

    def _history_response(
        self, account_id: UUID, period: str
    ) -> PortfolioHistoryResponse:
        start_date = (
            date.today() - timedelta(days=HISTORY_DAYS[period])
            if period != "ALL"
            else None
        )
        snapshots = self.repo.snapshots_since(account_id, start_date)
        indices = self.market_repo.kospi_since(
            start_date - timedelta(days=7) if start_date else None
        )
        items = build_history_points(snapshots, indices)
        return PortfolioHistoryResponse(
            account_id=account_id,
            period=period,
            benchmark_name="KOSPI",
            items=items,
        )
