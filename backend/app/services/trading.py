"""사람과 모델 주문이 공통으로 사용하는 내부 가상 체결 service."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceError
from app.models import CashLedger, Execution, Order, Position
from app.repositories import TradingRepository
from app.schemas.api import OrderCreateRequest
from app.services.market import MarketService


class TradingService:
    def __init__(self, session: Session, market: MarketService | None = None) -> None:
        self.session = session
        self.repo = TradingRepository(session)
        self.market = market or MarketService()

    def execute_market_order(self, user_id: int, request: OrderCreateRequest) -> Order:
        account = self.repo.owned_account(request.account_id, user_id)
        if not account:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        existing = self.repo.order_by_idempotency(account.id, request.idempotency_key)
        if existing:
            self._validate_idempotent_order(existing, request)
            self.session.rollback()
            return existing

        # 외부 가격 조회 전에 소유권과 멱등 재시도를 처리한다. 조회 transaction도 먼저 종료한다.
        self.session.rollback()
        price, _, _ = self.market.get_price(request.stock_code)
        try:
            account = self.repo.owned_account(request.account_id, user_id, lock=True)
            if not account:
                raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
            if account.status != "ACTIVE":
                raise ServiceError("ACCOUNT_INACTIVE", "거래할 수 없는 계좌입니다.", 409)

            existing = self.repo.order_by_idempotency(account.id, request.idempotency_key)
            if existing:
                self._validate_idempotent_order(existing, request)
                self.session.rollback()
                return existing

            total = (price * request.quantity).quantize(Decimal("0.01"))
            position = self.repo.position(account.id, request.stock_code, lock=True)
            if request.side == "BUY" and account.cash_balance < total:
                raise ServiceError("INSUFFICIENT_CASH", "주문 가능한 현금이 부족합니다.", 409)
            if request.side == "SELL" and (not position or position.quantity < request.quantity):
                raise ServiceError("INSUFFICIENT_POSITION", "매도 가능한 보유수량이 부족합니다.", 409)

            order = Order(
                account_id=account.id,
                stock_code=request.stock_code,
                side=request.side,
                order_type="MARKET",
                quantity=request.quantity,
                requested_price=price,
                status="FILLED",
                idempotency_key=request.idempotency_key,
            )
            self.session.add(order)
            self.session.flush()

            if request.side == "BUY":
                old_quantity = position.quantity if position else 0
                old_cost = (position.average_price * old_quantity) if position else Decimal("0")
                if not position:
                    position = Position(account_id=account.id, stock_code=request.stock_code, quantity=0, average_price=price, realized_profit=0)
                    self.session.add(position)
                position.quantity = old_quantity + request.quantity
                position.average_price = ((old_cost + total) / position.quantity).quantize(Decimal("0.0001"))
                account.cash_balance -= total
                cash_amount = -total
            else:
                assert position is not None
                realized = ((price - position.average_price) * request.quantity).quantize(Decimal("0.01"))
                position.quantity -= request.quantity
                position.realized_profit += realized
                account.cash_balance += total
                cash_amount = total

            self.session.add(
                Execution(order_id=order.id, account_id=account.id, stock_code=request.stock_code, side=request.side, quantity=request.quantity, execution_price=price)
            )
            self.session.add(
                CashLedger(account_id=account.id, transaction_type=request.side, amount=cash_amount, balance_after=account.cash_balance, reference_type="ORDER", reference_id=str(order.id))
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return order

    @staticmethod
    def _validate_idempotent_order(existing: Order, request: OrderCreateRequest) -> None:
        if existing.stock_code != request.stock_code or existing.side != request.side or existing.quantity != request.quantity:
            raise ServiceError("IDEMPOTENCY_CONFLICT", "동일 요청 키가 다른 주문에 사용되었습니다.", 409)
