"""Deterministic Algorithm v2.3 planner and exact-plan executor (fix1)."""

from datetime import UTC, datetime
from decimal import Decimal

from app.core.errors import NotFoundError, ServiceError
from app.schemas.api import OrderCreateRequest
from app.trading_engine.contracts import EngineOrder, EngineRunRequest, EngineRunResponse
from app.trading_engine.model_loader_fix1 import load_model_module_fix1


class IntegratedTradingEngineFix1:
    def __init__(self, repository, market, trading_service, model_module=None) -> None:
        self.repo = repository
        self.market = market
        self.trading = trading_service
        self.model_module = model_module or load_model_module_fix1()
        self.model = self.model_module.FinConVer23Model()

    def _account(self, user_id: int, request: EngineRunRequest, *, lock: bool = False):
        account = self.repo.owned_account(request.account_id, user_id, lock=lock)
        if account is None:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        if account.status != "ACTIVE":
            raise ServiceError("ACCOUNT_INACTIVE", "거래할 수 없는 계좌입니다.", 409)
        return account

    def plan(self, user_id: int, request: EngineRunRequest) -> EngineRunResponse:
        account = self._account(user_id, request)
        positions = [item for item in self.repo.positions(account.id) if item.quantity > 0]
        symbols = sorted(set(item.stock_code for item in positions) | set(request.signal.target_weights))
        prices: dict[str, Decimal] = {}
        for symbol in symbols:
            price, _, _ = self.market.get_price(symbol)
            prices[symbol] = Decimal(price)

        advice = request.coordinator_advice
        model_plan = self.model.plan(
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
                stock_code=item.stock_code,
                side=item.side,
                quantity=item.quantity,
                reference_price=item.reference_price,
                amount=item.amount,
                reason=item.reason,
                target_weight=item.target_weight,
                idempotency_key=item.idempotency_key,
            )
            for item in model_plan.orders
        ]
        orders.sort(key=lambda order: (order.side == "BUY", order.stock_code))
        return EngineRunResponse(
            account_id=request.account_id,
            generated_at=datetime.now(UTC),
            execution_mode="DRY_RUN",
            orders=orders,
            blocked_reasons=model_plan.blocked_reasons,
            coordinator_request_id=advice.request_id if advice else None,
        )

    def execute_plan(
        self, user_id: int, request: EngineRunRequest, plan: EngineRunResponse
    ) -> EngineRunResponse:
        """Execute only the already validated plan; never recalculate it."""
        account = self._account(user_id, request, lock=True)
        if account.operation_mode != "AUTO":
            return plan.model_copy(update={
                "execution_mode": "DRY_RUN",
                "blocked_reasons": [*plan.blocked_reasons, "PROPOSAL_ONLY_SEMI_AUTO"],
            })
        if len(plan.orders) > 1:
            raise ServiceError(
                "ATOMIC_BATCH_EXECUTION_REQUIRED",
                "여러 리밸런싱 주문은 원자적 배치 체결 구현 전까지 실행할 수 없습니다.",
                409,
            )
        for order in plan.orders:
            self.trading.execute_market_order(user_id, OrderCreateRequest(
                account_id=request.account_id,
                stock_code=order.stock_code,
                side=order.side,
                quantity=order.quantity,
                idempotency_key=order.idempotency_key,
            ))
            order.status = "FILLED"
        return plan.model_copy(update={"execution_mode": "PAPER", "orders": plan.orders})

    def run(self, user_id: int, request: EngineRunRequest) -> EngineRunResponse:
        plan = self.plan(user_id, request)
        return self.execute_plan(user_id, request, plan) if request.execute else plan
