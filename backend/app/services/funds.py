"""내부 가상계좌의 추가투자·비례매도 출금을 원자적으로 처리한다."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceError
from app.models import CashLedger, FundOperation, FundOperationOrder
from app.repositories import TradingRepository
from app.schemas.api import (
    FundOperationRequest,
    FundOperationResponse,
    FundSummaryResponse,
    FundTradeResponse,
    OrderCreateRequest,
)
from app.services.market import MarketService
from app.services.portfolio import calculate_return, validate_target_weights
from app.services.trading import MIN_ORDER_AMOUNT, TradingService


MONEY = Decimal("0.01")
QUANTITY = Decimal("0.00000001")
KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class PriceSnapshot:
    price: Decimal
    as_of: datetime
    source: str


class FundOperationService:
    """외부 송금 없이 가상 현금·포지션·원금만 변경한다."""

    def __init__(
        self,
        session: Session,
        market: MarketService | None = None,
        trading: TradingService | None = None,
    ) -> None:
        self.session = session
        self.repo = TradingRepository(session)
        self.market = market or MarketService()
        self.trading = trading or TradingService(session, self.market)

    def summary(self, user_id: int, account_id: UUID) -> FundSummaryResponse:
        account = self.repo.owned_account(account_id, user_id)
        if account is None:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        positions = [position for position in self.repo.positions(account.id) if position.quantity > 0]
        prices = self._load_prices({position.stock_code for position in positions})
        return self._summary(account, positions, prices)

    def add_investment(
        self,
        user_id: int,
        account_id: UUID,
        request: FundOperationRequest,
    ) -> FundOperationResponse:
        account = self._active_owned_account(user_id, account_id)
        existing = self.repo.fund_operation_by_idempotency(
            account.id, request.idempotency_key
        )
        if existing is not None:
            self._validate_replay(existing, "ADDITIONAL_INVESTMENT", request.amount)
            return self._operation_response(existing, account)
        if not account.selected_strategy_id:
            raise ServiceError(
                "STRATEGY_NOT_SELECTED",
                "추가투자에 사용할 전략이 선택되지 않았습니다.",
                409,
            )

        effective_on = datetime.now(KST).date()
        target_weights = self.repo.target_weights(
            account.selected_strategy_id, effective_on
        )
        if not target_weights:
            raise ServiceError(
                "STRATEGY_TARGET_WEIGHTS_UNAVAILABLE",
                "현재 적용할 수 있는 전략 목표 비중이 없습니다.",
                409,
            )
        validate_target_weights(
            target_weights,
            allow_cash_buffer=account.selected_strategy_id == "momentum",
        )
        current_positions = [
            position for position in self.repo.positions(account.id) if position.quantity > 0
        ]
        price_codes = set(target_weights) | {
            position.stock_code for position in current_positions
        }
        prices = self._load_prices(price_codes)

        # 읽기 transaction을 끝낸 뒤 계좌를 잠가 일반 주문과 동일한 lock 순서를 사용한다.
        self.session.rollback()
        try:
            account = self._locked_active_owned_account(user_id, account_id)
            existing = self.repo.fund_operation_by_idempotency(
                account.id, request.idempotency_key
            )
            if existing is not None:
                self._validate_replay(
                    existing, "ADDITIONAL_INVESTMENT", request.amount
                )
                self.session.rollback()
                return self._operation_response(existing, account)
            positions = [
                position
                for position in self.repo.positions(account.id)
                if position.quantity > 0
            ]
            self._ensure_price_snapshot_covers(positions, prices)
            principal_before = self._principal(account)
            total_before = self._total_assets(account.cash_balance, positions, prices)
            operation = FundOperation(
                id=uuid4(),
                account_id=account.id,
                operation_type="ADDITIONAL_INVESTMENT",
                status="PROCESSING",
                requested_amount=request.amount,
                executed_amount=Decimal("0"),
                principal_before=principal_before,
                principal_after=principal_before,
                total_assets_before=total_before,
                total_assets_after=total_before,
                idempotency_key=request.idempotency_key,
            )
            self.session.add(operation)
            self.session.flush()

            account.cash_balance = (Decimal(account.cash_balance) + request.amount).quantize(MONEY)
            account.invested_principal = (principal_before + request.amount).quantize(MONEY)
            self.session.add(
                CashLedger(
                    account_id=account.id,
                    transaction_type="ADDITIONAL_INVESTMENT",
                    amount=request.amount,
                    balance_after=account.cash_balance,
                    reference_type="FUND_OPERATION",
                    reference_id=str(operation.id),
                )
            )

            for stock_code, weight in sorted(target_weights.items()):
                allocated = (request.amount * Decimal(weight)).quantize(
                    MONEY, rounding=ROUND_DOWN
                )
                if allocated < MIN_ORDER_AMOUNT:
                    continue
                price = prices[stock_code].price
                quantity = (allocated / price).quantize(
                    QUANTITY, rounding=ROUND_DOWN
                )
                if quantity <= 0:
                    continue
                order = self.trading.execute_locked_market_order(
                    account,
                    OrderCreateRequest(
                        account_id=account.id,
                        stock_code=stock_code,
                        side="BUY",
                        quantity=quantity,
                        idempotency_key=f"fund-{operation.id.hex}-{stock_code}-buy",
                    ),
                    price,
                )
                actual = (price * quantity).quantize(MONEY)
                self.session.add(
                    FundOperationOrder(
                        fund_operation_id=operation.id,
                        order_id=order.id,
                        allocated_amount=actual,
                        applied_weight=weight,
                    )
                )

            operation.status = "COMPLETED"
            operation.executed_amount = request.amount
            operation.principal_after = account.invested_principal
            operation.total_assets_after = (total_before + request.amount).quantize(MONEY)
            operation.completed_at = datetime.now(KST)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        positions = [
            position for position in self.repo.positions(account.id) if position.quantity > 0
        ]
        return self._operation_response(operation, account, positions, prices)

    def withdraw(
        self,
        user_id: int,
        account_id: UUID,
        request: FundOperationRequest,
    ) -> FundOperationResponse:
        account = self._active_owned_account(user_id, account_id)
        existing = self.repo.fund_operation_by_idempotency(
            account.id, request.idempotency_key
        )
        if existing is not None:
            self._validate_replay(existing, "WITHDRAWAL", request.amount)
            return self._operation_response(existing, account)
        current_positions = [
            position for position in self.repo.positions(account.id) if position.quantity > 0
        ]
        prices = self._load_prices(
            {position.stock_code for position in current_positions}
        )

        self.session.rollback()
        try:
            account = self._locked_active_owned_account(user_id, account_id)
            existing = self.repo.fund_operation_by_idempotency(
                account.id, request.idempotency_key
            )
            if existing is not None:
                self._validate_replay(existing, "WITHDRAWAL", request.amount)
                self.session.rollback()
                return self._operation_response(existing, account)
            positions = [
                position
                for position in self.repo.positions(account.id)
                if position.quantity > 0
            ]
            self._ensure_price_snapshot_covers(positions, prices)
            values = self._position_values(positions, prices)
            position_total = sum(values.values(), Decimal("0")).quantize(MONEY)
            total_before = (Decimal(account.cash_balance) + position_total).quantize(MONEY)
            executable_positions = [
                position
                for position in positions
                if values[position.stock_code] >= MIN_ORDER_AMOUNT
            ]
            executable_total = sum(
                (values[position.stock_code] for position in executable_positions),
                Decimal("0"),
            ).quantize(MONEY)
            withdrawable = (
                Decimal(account.cash_balance) + executable_total
            ).quantize(MONEY)
            if request.amount > withdrawable:
                raise ServiceError(
                    "INSUFFICIENT_WITHDRAWABLE_ASSETS",
                    "출금 가능 금액보다 큰 금액을 요청했습니다.",
                    409,
                )
            principal_before = self._principal(account)
            total_after = (total_before - request.amount).quantize(MONEY)
            principal_after = (
                Decimal("0")
                if total_before == 0
                else (principal_before * total_after / total_before).quantize(MONEY)
            )
            operation = FundOperation(
                id=uuid4(),
                account_id=account.id,
                operation_type="WITHDRAWAL",
                status="PROCESSING",
                requested_amount=request.amount,
                executed_amount=Decimal("0"),
                principal_before=principal_before,
                principal_after=principal_before,
                total_assets_before=total_before,
                total_assets_after=total_before,
                idempotency_key=request.idempotency_key,
            )
            self.session.add(operation)
            self.session.flush()

            sell_target = min(request.amount, executable_total)
            allocations = self._proportional_allocations(
                sell_target, executable_positions, values, executable_total
            )
            for position, allocated in allocations:
                if allocated < MIN_ORDER_AMOUNT:
                    continue
                price = prices[position.stock_code].price
                quantity = min(
                    position.quantity,
                    (allocated / price).quantize(QUANTITY, rounding=ROUND_UP),
                )
                if quantity <= 0:
                    continue
                weight = (
                    values[position.stock_code] / position_total
                    if position_total > 0
                    else Decimal("0")
                ).quantize(Decimal("0.00000001"))
                order = self.trading.execute_locked_market_order(
                    account,
                    OrderCreateRequest(
                        account_id=account.id,
                        stock_code=position.stock_code,
                        side="SELL",
                        quantity=quantity,
                        idempotency_key=(
                            f"fund-{operation.id.hex}-{position.stock_code}-sell"
                        ),
                    ),
                    price,
                )
                self.session.add(
                    FundOperationOrder(
                        fund_operation_id=operation.id,
                        order_id=order.id,
                        allocated_amount=(price * quantity).quantize(MONEY),
                        applied_weight=weight,
                    )
                )

            if Decimal(account.cash_balance) < request.amount:
                raise ServiceError(
                    "WITHDRAWAL_EXECUTION_SHORTFALL",
                    "수량 반올림 후 출금에 필요한 가상 현금을 확보하지 못했습니다.",
                    409,
                )
            account.cash_balance = (
                Decimal(account.cash_balance) - request.amount
            ).quantize(MONEY)
            account.invested_principal = principal_after
            self.session.add(
                CashLedger(
                    account_id=account.id,
                    transaction_type="WITHDRAWAL",
                    amount=-request.amount,
                    balance_after=account.cash_balance,
                    reference_type="FUND_OPERATION",
                    reference_id=str(operation.id),
                )
            )
            operation.status = "COMPLETED"
            operation.executed_amount = request.amount
            operation.principal_after = principal_after
            operation.total_assets_after = total_after
            operation.completed_at = datetime.now(KST)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        positions = [
            position for position in self.repo.positions(account.id) if position.quantity > 0
        ]
        return self._operation_response(operation, account, positions, prices)

    def _active_owned_account(self, user_id: int, account_id: UUID):
        account = self.repo.owned_account(account_id, user_id)
        if account is None:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        if account.status != "ACTIVE":
            raise ServiceError("ACCOUNT_INACTIVE", "거래할 수 없는 계좌입니다.", 409)
        return account

    def _locked_active_owned_account(self, user_id: int, account_id: UUID):
        account = self.repo.owned_account(account_id, user_id, lock=True)
        if account is None:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        if account.status != "ACTIVE":
            raise ServiceError("ACCOUNT_INACTIVE", "거래할 수 없는 계좌입니다.", 409)
        return account

    def _load_prices(self, stock_codes: set[str]) -> dict[str, PriceSnapshot]:
        prices: dict[str, PriceSnapshot] = {}
        for stock_code in sorted(stock_codes):
            price, as_of, source = self.market.get_price(stock_code)
            if price <= 0:
                raise ServiceError(
                    "MARKET_PRICE_UNAVAILABLE",
                    f"{stock_code} 종목의 유효한 현재가가 없습니다.",
                    503,
                )
            prices[stock_code] = PriceSnapshot(Decimal(price), as_of, source)
        return prices

    @staticmethod
    def _ensure_price_snapshot_covers(positions, prices: dict[str, PriceSnapshot]) -> None:
        missing = {
            position.stock_code
            for position in positions
            if position.stock_code not in prices
        }
        if missing:
            raise ServiceError(
                "PORTFOLIO_CHANGED",
                "가격 조회 중 포트폴리오가 변경되었습니다. 다시 시도해 주세요.",
                409,
            )

    @staticmethod
    def _principal(account) -> Decimal:
        value = getattr(account, "invested_principal", None)
        if value is None:
            value = getattr(account, "initial_cash", Decimal("0"))
        return Decimal(value).quantize(MONEY)

    @staticmethod
    def _position_values(positions, prices: dict[str, PriceSnapshot]) -> dict[str, Decimal]:
        return {
            position.stock_code: (
                Decimal(position.quantity) * prices[position.stock_code].price
            ).quantize(MONEY)
            for position in positions
        }

    def _total_assets(self, cash_balance, positions, prices) -> Decimal:
        return (
            Decimal(cash_balance)
            + sum(self._position_values(positions, prices).values(), Decimal("0"))
        ).quantize(MONEY)

    def _summary(self, account, positions, prices) -> FundSummaryResponse:
        position_values = self._position_values(positions, prices)
        position_total = sum(position_values.values(), Decimal("0")).quantize(MONEY)
        executable_total = sum(
            (
                value
                for value in position_values.values()
                if value >= MIN_ORDER_AMOUNT
            ),
            Decimal("0"),
        ).quantize(MONEY)
        total_assets = (Decimal(account.cash_balance) + position_total).quantize(MONEY)
        principal = self._principal(account)
        profit = (total_assets - principal).quantize(MONEY)
        return FundSummaryResponse(
            account_id=account.id,
            invested_principal=principal,
            cash_balance=account.cash_balance,
            position_evaluation_amount=position_total,
            total_assets=total_assets,
            valuation_profit=profit,
            return_rate=calculate_return(profit, principal),
            withdrawable_amount=(
                Decimal(account.cash_balance) + executable_total
            ).quantize(MONEY),
            valuation_as_of=max(
                (snapshot.as_of for snapshot in prices.values()), default=None
            ),
        )

    @staticmethod
    def _proportional_allocations(
        target: Decimal,
        positions,
        values: dict[str, Decimal],
        total: Decimal,
    ):
        if target <= 0 or total <= 0:
            return []
        ordered = sorted(positions, key=lambda item: item.stock_code)
        remaining = target
        allocations = []
        for index, position in enumerate(ordered):
            allocated = (
                remaining
                if index == len(ordered) - 1
                else (target * values[position.stock_code] / total).quantize(
                    MONEY, rounding=ROUND_DOWN
                )
            )
            allocated = min(allocated, values[position.stock_code])
            allocations.append((position, allocated))
            remaining -= allocated
        small_total = sum(
            (amount for _, amount in allocations if Decimal("0") < amount < MIN_ORDER_AMOUNT),
            Decimal("0"),
        )
        allocations = [
            (position, Decimal("0") if Decimal("0") < amount < MIN_ORDER_AMOUNT else amount)
            for position, amount in allocations
        ]
        if small_total:
            redistributed = []
            for position, amount in sorted(
                allocations,
                key=lambda item: values[item[0].stock_code] - item[1],
                reverse=True,
            ):
                capacity = values[position.stock_code] - amount
                addition = min(capacity, small_total)
                redistributed.append((position, amount + addition))
                small_total -= addition
            allocations = redistributed
        return sorted(allocations, key=lambda item: item[0].stock_code)

    def _operation_response(
        self,
        operation: FundOperation,
        account,
        positions=None,
        prices: dict[str, PriceSnapshot] | None = None,
    ) -> FundOperationResponse:
        if positions is None:
            positions = [
                position
                for position in self.repo.positions(account.id)
                if position.quantity > 0
            ]
        if prices is None:
            prices = self._load_prices(
                {position.stock_code for position in positions}
            )
        trades = []
        for link, order in self.repo.fund_operation_orders(operation.id):
            price = Decimal(order.requested_price or 0)
            trades.append(
                FundTradeResponse(
                    order_id=order.id,
                    stock_code=order.stock_code,
                    side=order.side,
                    applied_weight=link.applied_weight,
                    quantity=order.quantity,
                    execution_price=price,
                    transaction_amount=(price * order.quantity).quantize(MONEY),
                )
            )
        return FundOperationResponse(
            operation_id=operation.id,
            type=operation.operation_type,
            status="COMPLETED",
            requested_amount=operation.requested_amount,
            executed_amount=operation.executed_amount,
            principal_before=operation.principal_before,
            principal_after=operation.principal_after,
            portfolio=self._summary(account, positions, prices),
            trades=trades,
        )

    @staticmethod
    def _validate_replay(
        operation: FundOperation,
        operation_type: str,
        amount: Decimal,
    ) -> None:
        if (
            operation.operation_type != operation_type
            or Decimal(operation.requested_amount) != Decimal(amount)
        ):
            raise ServiceError(
                "FUND_OPERATION_IDEMPOTENCY_CONFLICT",
                "같은 멱등성 키를 다른 가상 자금 요청에 사용할 수 없습니다.",
                409,
            )
        if operation.status != "COMPLETED":
            raise ServiceError(
                "FUND_OPERATION_IN_PROGRESS",
                "같은 가상 자금 요청이 처리 중입니다.",
                409,
            )
