"""FINCON-inspired deterministic portfolio model for Algorithm(ver2.3).

This module intentionally has no FastAPI, SQLAlchemy, broker or LLM dependency.
The server supplies normalized account/position/price data and owns execution.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from hashlib import sha256
from typing import Literal


ZERO = Decimal("0")
QTY_STEP = Decimal("0.00000001")
MODEL_VERSION = "fincon-ver23-v1"


@dataclass(frozen=True)
class PositionInput:
    stock_code: str
    quantity: Decimal


@dataclass
class PlannedOrder:
    stock_code: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    reference_price: Decimal
    amount: Decimal
    reason: Literal["STOP_LOSS", "REBALANCE"]
    target_weight: Decimal
    idempotency_key: str


@dataclass(frozen=True)
class ModelPlan:
    orders: list[PlannedOrder]
    blocked_reasons: list[str]


class FinConVer23Model:
    """Risk-first synthesis of v2.3 signals, coordinator advice and rebalancing."""

    @staticmethod
    def _quantity(amount: Decimal, price: Decimal) -> Decimal:
        return (amount / price).quantize(QTY_STEP, rounding=ROUND_DOWN)

    @staticmethod
    def _key(account_id: str, generated_at: str, symbol: str, side: str, reason: str) -> str:
        raw = f"{MODEL_VERSION}:{account_id}:{generated_at}:{symbol}:{side}:{reason}"
        return "engine-" + sha256(raw.encode()).hexdigest()[:40]

    def plan(
        self,
        *,
        account_id: str,
        generated_at: str,
        cash_balance: Decimal,
        positions: list[PositionInput],
        prices: dict[str, Decimal],
        target_weights: dict[str, Decimal],
        stop_prices: dict[str, Decimal],
        coordinator_blocked_symbols: set[str],
        coordinator_risk_flags: list[str],
        max_turnover: Decimal,
        min_order_amount: Decimal,
        cash_buffer: Decimal,
    ) -> ModelPlan:
        held = {item.stock_code: item for item in positions if item.quantity > 0}
        blocked = [f"COORDINATOR_RISK:{flag}" for flag in coordinator_risk_flags]
        values = {symbol: item.quantity * prices[symbol] for symbol, item in held.items()}
        total_assets = cash_balance + sum(values.values(), ZERO)
        if total_assets <= 0:
            return ModelPlan([], [*blocked, "NO_ASSETS"])

        orders: list[PlannedOrder] = []
        stopped: set[str] = set()
        for symbol, stop_price in stop_prices.items():
            position, price = held.get(symbol), prices.get(symbol)
            if position and price is not None and price <= stop_price:
                amount = (position.quantity * price).quantize(Decimal("0.01"))
                orders.append(self._order(account_id, generated_at, symbol, "SELL", position.quantity, price, amount, "STOP_LOSS", ZERO))
                stopped.add(symbol)

        investable = Decimal("1") - cash_buffer
        targets = {
            symbol: min(weight, investable)
            for symbol, weight in target_weights.items()
            if symbol not in stopped and symbol not in coordinator_blocked_symbols
        }
        blocked.extend(
            f"COORDINATOR_BLOCK:{symbol}"
            for symbol in sorted(coordinator_blocked_symbols & set(target_weights))
        )
        current = {symbol: value / total_assets for symbol, value in values.items()}
        deltas = {
            symbol: targets.get(symbol, ZERO) - current.get(symbol, ZERO)
            for symbol in set(current) | set(targets)
        }
        discretionary = [delta for symbol, delta in deltas.items() if symbol not in stopped]
        buys_weight = sum((delta for delta in discretionary if delta > 0), ZERO)
        sells_weight = sum((-delta for delta in discretionary if delta < 0), ZERO)
        turnover = max(buys_weight, sells_weight)  # includes balancing cash asset
        scale = min(Decimal("1"), max_turnover / turnover) if turnover > 0 else Decimal("1")

        candidates: list[PlannedOrder] = []
        for symbol in sorted(deltas):
            if symbol in stopped:
                continue
            delta = deltas[symbol] * scale
            amount = (abs(delta) * total_assets).quantize(Decimal("0.01"))
            if amount < min_order_amount:
                continue
            side = "BUY" if delta > 0 else "SELL"
            quantity = self._quantity(amount, prices[symbol])
            if side == "SELL":
                quantity = min(quantity, held[symbol].quantity if symbol in held else ZERO)
                amount = (quantity * prices[symbol]).quantize(Decimal("0.01"))
            if quantity > 0 and amount >= min_order_amount:
                candidates.append(self._order(account_id, generated_at, symbol, side, quantity, prices[symbol], amount, "REBALANCE", targets.get(symbol, ZERO)))

        sells = [order for order in candidates if order.side == "SELL"]
        buys = [order for order in candidates if order.side == "BUY"]
        available_cash = max(ZERO, cash_balance + sum(o.amount for o in sells) - total_assets * cash_buffer)
        for order in buys:
            if order.amount > available_cash:
                order.quantity = self._quantity(available_cash, order.reference_price)
                order.amount = (order.quantity * order.reference_price).quantize(Decimal("0.01"))
            available_cash -= order.amount
        orders.extend(sells)
        orders.extend(order for order in buys if order.amount >= min_order_amount and order.quantity > 0)
        return ModelPlan(orders, blocked)

    def _order(self, account_id, generated_at, symbol, side, quantity, price, amount, reason, target):
        return PlannedOrder(
            symbol, side, quantity, price, amount, reason, target,
            self._key(account_id, generated_at, symbol, side, reason),
        )
