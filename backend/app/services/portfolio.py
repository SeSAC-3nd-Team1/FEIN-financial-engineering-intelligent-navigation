"""실제 계좌·시세·KRX metadata를 결합해 포트폴리오 분석을 제공한다."""

from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceError
from app.integrations.kis.models import CurrentQuote
from app.repositories import TradingRepository
from app.repositories.market_data import MarketDataRepository
from app.schemas.api import (
    PortfolioContributionResponse,
    PortfolioHistoryPointResponse,
    PortfolioHistoryResponse,
    PortfolioResponse,
    PositionResponse,
    RebalancingProposalResponse,
)
from app.services.market import MarketService


HISTORY_DAYS = {"1M": 31, "3M": 93, "1Y": 366}
KST = timezone(timedelta(hours=9))


def calculate_return(profit: Decimal, purchase: Decimal) -> Decimal:
    return Decimal("0") if purchase == 0 else (profit / purchase * 100).quantize(Decimal("0.01"))


def calculate_weight(evaluation: Decimal, total_assets: Decimal) -> Decimal:
    return Decimal("0") if total_assets == 0 else (evaluation / total_assets * 100).quantize(Decimal("0.01"))


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
        target = (target_weights.get(stock_code, Decimal("0")) * 100).quantize(Decimal("0.01"))
        diff = (current - target).quantize(Decimal("0.01"))
        if diff == 0:
            continue
        proposals.append(RebalancingProposalResponse(
            stock_code=stock_code,
            stock_name=stock_names.get(stock_code),
            current_weight=current,
            target_weight=target,
            weight_diff=diff,
            action="SELL" if diff > 0 else "BUY",
            recommended_amount=(total_assets * abs(diff) / 100).quantize(Decimal("0.01")),
        ))
    return sorted(proposals, key=lambda item: item.recommended_amount, reverse=True)


def validate_target_weights(target_weights: dict[str, Decimal]) -> None:
    if target_weights and sum(target_weights.values(), Decimal("0")) != Decimal("1"):
        raise ServiceError(
            "INVALID_STRATEGY_TARGET_WEIGHTS",
            "전략 목표 비중 합계가 1이 아닙니다.",
            503,
        )


def build_history_points(snapshots: list, indices: list) -> list[PortfolioHistoryPointResponse]:
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
        while index_position < len(indices) and indices[index_position].trade_date <= snapshot.snapshot_date:
            latest_benchmark = indices[index_position].close_value
            index_position += 1
        if snapshot_index == 0:
            benchmark_base = latest_benchmark
        portfolio_rate = (
            ((snapshot.total_assets / first_assets) - 1) * 100
            if first_assets and first_assets > 0 else Decimal("0")
        )
        benchmark_rate = (
            ((latest_benchmark / benchmark_base) - 1) * 100
            if latest_benchmark is not None and benchmark_base else None
        )
        items.append(PortfolioHistoryPointResponse(
            date=snapshot.snapshot_date,
            total_assets=snapshot.total_assets,
            portfolio_return_rate=portfolio_rate.quantize(Decimal("0.01")),
            benchmark_return_rate=(
                benchmark_rate.quantize(Decimal("0.01")) if benchmark_rate is not None else None
            ),
        ))
    return items


class PortfolioService:
    def __init__(self, session: Session, market: MarketService | None = None) -> None:
        self.session = session
        self.repo = TradingRepository(session)
        self.market_repo = MarketDataRepository(session)
        self.market = market

    def evaluate(self, user_id: int, account_id: UUID) -> PortfolioResponse:
        account = self.repo.owned_account(account_id, user_id)
        if not account:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")

        return self._evaluate_account(account)

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
            quote_provider = self.market.get_quote

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
            purchase = (position.average_price * position.quantity).quantize(Decimal("0.01"))
            evaluation = (quote.price * position.quantity).quantize(Decimal("0.01"))
            profit = evaluation - purchase
            today_profit = (
                ((quote.price - quote.previous_close) * position.quantity).quantize(Decimal("0.01"))
                if quote.previous_close is not None else None
            )
            purchase_total += purchase
            evaluation_total += evaluation
            evaluated.append({
                "position": position, "quote": quote, "stock": stock,
                "purchase": purchase, "evaluation": evaluation,
                "profit": profit, "today_profit": today_profit,
            })

        total_assets = (account.cash_balance + evaluation_total).quantize(Decimal("0.01"))
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
            if all_today_prices_available else None
        )

        for item in evaluated:
            position = item["position"]
            quote = item["quote"]
            stock = item["stock"]
            weight = calculate_weight(item["evaluation"], total_assets)
            stock_name = stock.stock_name if stock else None
            current_weights[position.stock_code] = weight
            stock_names[position.stock_code] = stock_name
            rows.append(PositionResponse(
                stock_code=position.stock_code, stock_name=stock_name,
                sector=stock.sector if stock else None, quantity=position.quantity,
                average_price=position.average_price, current_price=quote.price,
                previous_close=quote.previous_close, change_rate=quote.change_rate,
                purchase_amount=item["purchase"], evaluation_amount=item["evaluation"],
                unrealized_profit=item["profit"],
                return_rate=calculate_return(item["profit"], item["purchase"]),
                realized_profit=position.realized_profit, weight=weight,
                today_profit=item["today_profit"], price_source=quote.source,
                price_as_of=quote.as_of,
            ))
            if item["today_profit"] is not None:
                share = (
                    (item["today_profit"] / today_profit * 100).quantize(Decimal("0.01"))
                    if all_today_prices_available and today_profit != Decimal("0") else None
                )
                contributions.append(PortfolioContributionResponse(
                    stock_code=position.stock_code, stock_name=stock_name,
                    amount=item["today_profit"], share_rate=share,
                ))
        contributions.sort(key=lambda item: item.amount, reverse=True)

        targets = (
            self.repo.target_weights(account.selected_strategy_id, effective_on)
            if include_strategy and account.selected_strategy_id else {}
        )
        validate_target_weights(targets)
        for stock_code in targets:
            if stock_code not in stock_names:
                stock = self.market_repo.stock(stock_code)
                stock_names[stock_code] = stock.stock_name if stock else None
        proposals = calculate_rebalancing(total_assets, current_weights, targets, stock_names) if targets else []

        return PortfolioResponse(
            account_id=account.id, cash_balance=account.cash_balance,
            total_purchase_amount=purchase_total, total_evaluation_amount=evaluation_total,
            total_assets=total_assets, unrealized_profit=unrealized,
            realized_profit=realized_total, return_rate=calculate_return(unrealized, purchase_total),
            today_profit=today_profit, top_contributor=contributions[0] if contributions else None,
            contributions=contributions, strategy_targets_available=bool(targets),
            rebalancing_proposals=proposals, positions=rows,
        )

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
                    quote_provider=lambda stock_code: self._closing_quote(stock_code, snapshot_date),
                    effective_on=snapshot_date,
                    include_strategy=False,
                )
                self.repo.save_snapshot(
                    account.id, snapshot_date, cash_balance=response.cash_balance,
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

    def history(self, user_id: int, account_id: UUID, period: str) -> PortfolioHistoryResponse:
        account = self.repo.owned_account(account_id, user_id)
        if not account:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        start_date = date.today() - timedelta(days=HISTORY_DAYS[period]) if period != "ALL" else None
        snapshots = self.repo.snapshots_since(account_id, start_date)
        indices = self.market_repo.kospi_since(start_date - timedelta(days=7) if start_date else None)
        items = build_history_points(snapshots, indices)
        return PortfolioHistoryResponse(
            account_id=account_id, period=period, benchmark_name="KOSPI", items=items,
        )
