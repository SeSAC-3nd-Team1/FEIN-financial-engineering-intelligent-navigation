"""현재가를 결합해 조회 시점 포트폴리오 평가를 계산한다."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.repositories import TradingRepository
from app.schemas.api import PortfolioResponse, PositionResponse
from app.services.market import MarketService


def calculate_return(profit: Decimal, purchase: Decimal) -> Decimal:
    return Decimal("0") if purchase == 0 else (profit / purchase * 100).quantize(Decimal("0.01"))


class PortfolioService:
    def __init__(self, session: Session, market: MarketService | None = None) -> None:
        self.repo = TradingRepository(session)
        self.market = market or MarketService()

    def evaluate(self, user_id: int, account_id: UUID) -> PortfolioResponse:
        account = self.repo.owned_account(account_id, user_id)
        if not account:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        rows: list[PositionResponse] = []
        purchase_total = Decimal("0")
        evaluation_total = Decimal("0")
        realized_total = Decimal("0")
        for position in self.repo.positions(account_id):
            if position.quantity == 0:
                realized_total += position.realized_profit
                continue
            price, _, _ = self.market.get_price(position.stock_code)
            purchase = (position.average_price * position.quantity).quantize(Decimal("0.01"))
            evaluation = (price * position.quantity).quantize(Decimal("0.01"))
            profit = evaluation - purchase
            purchase_total += purchase
            evaluation_total += evaluation
            realized_total += position.realized_profit
            rows.append(PositionResponse(
                stock_code=position.stock_code, quantity=position.quantity, average_price=position.average_price,
                current_price=price, purchase_amount=purchase, evaluation_amount=evaluation,
                unrealized_profit=profit, return_rate=calculate_return(profit, purchase), realized_profit=position.realized_profit,
            ))
        unrealized = evaluation_total - purchase_total
        return PortfolioResponse(
            account_id=account.id, cash_balance=account.cash_balance, total_purchase_amount=purchase_total,
            total_evaluation_amount=evaluation_total, total_assets=account.cash_balance + evaluation_total,
            unrealized_profit=unrealized, realized_profit=realized_total,
            return_rate=calculate_return(unrealized, purchase_total), positions=rows,
        )
