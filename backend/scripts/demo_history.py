"""시장 종가를 날짜순으로 재생하는 데모 포트폴리오 시뮬레이터."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_FLOOR


MONEY = Decimal("0.01")
PRICE = Decimal("0.0001")
QUANTITY = Decimal("0.00000001")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY)


def quantity_for(amount: Decimal, price: Decimal) -> Decimal:
    return (amount / price).quantize(QUANTITY, rounding=ROUND_FLOOR)


@dataclass
class Holding:
    quantity: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")
    realized_profit: Decimal = Decimal("0")


@dataclass(frozen=True)
class Trade:
    trade_date: date
    sequence: int
    stock_code: str
    side: str
    quantity: Decimal
    price: Decimal
    amount: Decimal
    cash_after: Decimal
    reason: str


@dataclass(frozen=True)
class Snapshot:
    snapshot_date: date
    cash_balance: Decimal
    total_purchase_amount: Decimal
    total_evaluation_amount: Decimal
    total_assets: Decimal
    unrealized_profit: Decimal
    realized_profit: Decimal
    return_rate: Decimal


@dataclass(frozen=True)
class SimulationResult:
    trades: tuple[Trade, ...]
    snapshots: tuple[Snapshot, ...]
    holdings: dict[str, Holding]
    final_cash: Decimal


def simulate_history(
    trading_dates: list[date],
    closes: dict[str, dict[date, Decimal]],
    target_weights: dict[str, Decimal],
    *,
    initial_cash: Decimal,
    rebalance_every: int = 21,
    target_weight_schedule: dict[int, dict[str, Decimal]] | None = None,
) -> SimulationResult:
    """최초 매수 후 일정 거래일마다 목표 비중으로 되돌린다.

    외부 입출금은 만들지 않는다. 따라서 첫 스냅샷 대비 총자산 변화가 그대로
    기간 수익률이 되며 현재 PortfolioService의 차트 산식과 일치한다.
    """

    if not trading_dates:
        raise ValueError("거래일이 없습니다.")
    if initial_cash <= 0:
        raise ValueError("초기 투자금은 0보다 커야 합니다.")
    has_explicit_schedule = bool(target_weight_schedule)
    schedules = {0: target_weights, **(target_weight_schedule or {})}
    if any(index < 0 or index >= len(trading_dates) for index in schedules):
        raise ValueError("목표 비중 변경 거래일이 전체 기간을 벗어났습니다.")
    if any(
        not weights or sum(weights.values(), Decimal("0")) > Decimal("1")
        for weights in schedules.values()
    ):
        raise ValueError("목표 비중 합계는 0보다 크고 1 이하여야 합니다.")
    stock_codes = tuple(sorted({code for weights in schedules.values() for code in weights}))
    for stock_code in stock_codes:
        missing = [day for day in trading_dates if day not in closes.get(stock_code, {})]
        if missing:
            raise ValueError(f"{stock_code} 종가가 없는 거래일이 있습니다: {missing[0]}")

    def weights_for(day_index: int) -> dict[str, Decimal]:
        effective_index = max(index for index in schedules if index <= day_index)
        return schedules[effective_index]

    cash = money(initial_cash)
    holdings = {stock_code: Holding() for stock_code in stock_codes}
    trades: list[Trade] = []
    snapshots: list[Snapshot] = []
    sequence = 0

    def execute(day: date, stock_code: str, side: str, qty: Decimal, reason: str) -> None:
        nonlocal cash, sequence
        if qty <= 0:
            return
        price = closes[stock_code][day].quantize(PRICE)
        amount = money(price * qty)
        if amount < Decimal("1"):
            return
        holding = holdings[stock_code]
        if side == "BUY":
            if amount > cash:
                return
            old_cost = holding.average_price * holding.quantity
            holding.quantity += qty
            holding.average_price = (
                (old_cost + amount) / holding.quantity
            ).quantize(PRICE)
            cash = money(cash - amount)
        else:
            if qty > holding.quantity:
                raise ValueError(f"{stock_code} 매도 수량이 보유 수량을 초과합니다.")
            holding.realized_profit = money(
                holding.realized_profit + (price - holding.average_price) * qty
            )
            holding.quantity -= qty
            cash = money(cash + amount)
        sequence += 1
        trades.append(
            Trade(day, sequence, stock_code, side, qty, price, amount, cash, reason)
        )

    first_day = trading_dates[0]
    for stock_code, weight in weights_for(0).items():
        target_amount = money(initial_cash * weight)
        execute(
            first_day,
            stock_code,
            "BUY",
            quantity_for(target_amount, closes[stock_code][first_day]),
            "INITIAL_ALLOCATION",
        )

    for day_index, day in enumerate(trading_dates):
        schedule_changed = day_index > 0 and day_index in schedules
        periodic_rebalance = not has_explicit_schedule and day_index % rebalance_every == 0
        if day_index > 0 and (periodic_rebalance or schedule_changed):
            active_weights = weights_for(day_index)
            evaluations = {
                code: money(holding.quantity * closes[code][day])
                for code, holding in holdings.items()
            }
            assets = money(cash + sum(evaluations.values(), Decimal("0")))

            # 매도를 먼저 실행해야 이후 부족 비중 매수에 사용할 현금이 생긴다.
            for side in ("SELL", "BUY"):
                for stock_code in stock_codes:
                    weight = active_weights.get(stock_code, Decimal("0"))
                    delta = money(assets * weight - evaluations[stock_code])
                    if side == "SELL" and delta < Decimal("-1"):
                        execute(
                            day,
                            stock_code,
                            side,
                            (
                                holdings[stock_code].quantity
                                if weight == 0
                                else min(
                                    holdings[stock_code].quantity,
                                    quantity_for(-delta, closes[stock_code][day]),
                                )
                            ),
                            "MONTHLY_REBALANCE",
                        )
                    elif side == "BUY" and delta > Decimal("1"):
                        affordable = quantity_for(cash, closes[stock_code][day])
                        execute(
                            day,
                            stock_code,
                            side,
                            min(
                                quantity_for(delta, closes[stock_code][day]),
                                affordable,
                            ),
                            "MONTHLY_REBALANCE",
                        )

        purchase = sum(
            (money(item.quantity * item.average_price) for item in holdings.values()),
            Decimal("0"),
        )
        evaluation = sum(
            (
                money(holdings[code].quantity * closes[code][day])
                for code in stock_codes
            ),
            Decimal("0"),
        )
        realized = sum(
            (item.realized_profit for item in holdings.values()), Decimal("0")
        )
        assets = money(cash + evaluation)
        valuation_profit = money(assets - initial_cash)
        snapshots.append(
            Snapshot(
                snapshot_date=day,
                cash_balance=cash,
                total_purchase_amount=money(purchase),
                total_evaluation_amount=money(evaluation),
                total_assets=assets,
                unrealized_profit=money(evaluation - purchase),
                realized_profit=money(realized),
                return_rate=money(valuation_profit / initial_cash * 100),
            )
        )

    return SimulationResult(tuple(trades), tuple(snapshots), holdings, cash)
