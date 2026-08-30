"""Server adapter for the model implemented in ``output/fincon_ver23_model.py``."""

from datetime import UTC, datetime
from decimal import Decimal

from app.schemas.api import OrderCreateRequest
from app.trading_engine.contracts import EngineOrder, EngineRunRequest, EngineRunResponse
from app.trading_engine.model_loader import load_model_module


class IntegratedTradingEngine:
    def __init__(self, repository, market, trading_service, model_module=None) -> None:
        self.repo = repository
        self.market = market
        self.trading = trading_service
        self.model_module = model_module or load_model_module()
        self.model = self.model_module.FinConVer23Model()

    def run(self, user_id: int, request: EngineRunRequest) -> EngineRunResponse:
        account = self.repo.owned_account(request.account_id, user_id)
        if account is None:
            from app.core.errors import NotFoundError
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        if account.status != "ACTIVE":
            from app.core.errors import ServiceError
            raise ServiceError("ACCOUNT_INACTIVE", "거래할 수 없는 계좌입니다.", 409)

        positions = [item for item in self.repo.positions(account.id) if item.quantity > 0]
        symbols = sorted(set(item.stock_code for item in positions) | set(request.signal.target_weights))
        prices: dict[str, Decimal] = {}
        for symbol in symbols:
            price, _, _ = self.market.get_price(symbol)
            prices[symbol] = Decimal(price)

        advice = request.coordinator_advice
        plan = self.model.plan(
            account_id=str(request.account_id),
            generated_at=request.signal.generated_at.isoformat(),
            cash_balance=account.cash_balance,
            positions=[self.model_module.PositionInput(item.stock_code, item.quantity) for item in positions],
            prices=prices,
            target_weights=request.signal.target_weights,
            stop_prices=request.signal.stop_prices,
            coordinator_blocked_symbols=set(advice.blocked_symbols if advice else []),
            coordinator_risk_flags=list(advice.risk_flags if advice else []),
            max_turnover=request.max_turnover,
            min_order_amount=request.min_order_amount,
            cash_buffer=request.cash_buffer,
        )
        orders = [
            EngineOrder(
                stock_code=item.stock_code, side=item.side, quantity=item.quantity,
                reference_price=item.reference_price, amount=item.amount,
                reason=item.reason, target_weight=item.target_weight,
                idempotency_key=item.idempotency_key,
            )
            for item in plan.orders
        ]
        if request.execute:
            orders.sort(key=lambda order: (order.side == "BUY", order.stock_code))
            for order in orders:
                self.trading.execute_market_order(user_id, OrderCreateRequest(
                    account_id=request.account_id, stock_code=order.stock_code,
                    side=order.side, quantity=order.quantity,
                    idempotency_key=order.idempotency_key,
                ))
                order.status = "FILLED"
        return EngineRunResponse(
            account_id=request.account_id,
            generated_at=datetime.now(UTC),
            execution_mode="PAPER" if request.execute else "DRY_RUN",
            orders=orders,
            blocked_reasons=plan.blocked_reasons,
            coordinator_request_id=advice.request_id if advice else None,
        )
