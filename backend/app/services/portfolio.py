"""실제 계좌·시세·KRX metadata를 결합해 포트폴리오 분석을 제공한다."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
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


def build_history_points(snapshots: list, indices: list) -> list[PortfolioHistoryPointResponse]:
    """실제 snapshot 날짜에 맞춰 포트폴리오와 직전 KOSPI 수익률을 정규화한다."""

    if not snapshots:
        return []
    first_assets = snapshots[0].total_assets
    benchmark_base: Decimal | None = None
    latest_benchmark: Decimal | None = None
    index_position = 0
    items: list[PortfolioHistoryPointResponse] = []
    for snapshot in snapshots:
        while index_position < len(indices) and indices[index_position].trade_date <= snapshot.snapshot_date:
            latest_benchmark = indices[index_position].close_value
            benchmark_base = benchmark_base or latest_benchmark
            index_position += 1
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
        self.market = market or MarketService()

    def evaluate(self, user_id: int, account_id: UUID) -> PortfolioResponse:
        account = self.repo.owned_account(account_id, user_id)
        if not account:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")

        evaluated: list[dict] = []
        purchase_total = Decimal("0")
        evaluation_total = Decimal("0")
        realized_total = Decimal("0")
        for position in self.repo.positions(account_id):
            realized_total += position.realized_profit
            if position.quantity == 0:
                continue
            quote = self.market.get_quote(position.stock_code)
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
        known_today = [item["today_profit"] for item in evaluated if item["today_profit"] is not None]
        today_profit = sum(known_today, Decimal("0")) if known_today else None

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
                    if today_profit not in (None, Decimal("0")) else None
                )
                contributions.append(PortfolioContributionResponse(
                    stock_code=position.stock_code, stock_name=stock_name,
                    amount=item["today_profit"], share_rate=share,
                ))
        contributions.sort(key=lambda item: item.amount, reverse=True)

        targets = (
            self.repo.target_weights(account.selected_strategy_id, date.today())
            if account.selected_strategy_id else {}
        )
        for stock_code in targets:
            if stock_code not in stock_names:
                stock = self.market_repo.stock(stock_code)
                stock_names[stock_code] = stock.stock_name if stock else None
        proposals = calculate_rebalancing(total_assets, current_weights, targets, stock_names) if targets else []

        response = PortfolioResponse(
            account_id=account.id, cash_balance=account.cash_balance,
            total_purchase_amount=purchase_total, total_evaluation_amount=evaluation_total,
            total_assets=total_assets, unrealized_profit=unrealized,
            realized_profit=realized_total, return_rate=calculate_return(unrealized, purchase_total),
            today_profit=today_profit, top_contributor=contributions[0] if contributions else None,
            contributions=contributions, strategy_targets_available=bool(targets),
            rebalancing_proposals=proposals, positions=rows,
        )
        try:
            self.repo.save_snapshot(
                account.id, date.today(), cash_balance=account.cash_balance,
                total_purchase_amount=purchase_total, total_evaluation_amount=evaluation_total,
                total_assets=total_assets, unrealized_profit=unrealized,
                realized_profit=realized_total, return_rate=response.return_rate,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return response

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
