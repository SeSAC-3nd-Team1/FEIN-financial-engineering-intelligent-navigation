"""현재 price-momentum-v1 규칙을 과거 시점별로 재현한다."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import math
from statistics import stdev


TOP_N = 5
TARGET_WEIGHT = Decimal("0.19")


@dataclass(frozen=True)
class PriceBar:
    stock_code: str
    trade_date: date
    open_price: Decimal | None
    high_price: Decimal | None
    low_price: Decimal | None
    close_price: Decimal | None
    volume: int | None
    trading_value: Decimal | None
    market_cap: Decimal | None


def monthly_signal_dates(trading_dates: list[date]) -> list[date]:
    """첫 거래일과 이후 각 달의 첫 KOSPI 거래일을 반환한다."""

    selected: list[date] = []
    previous_month: tuple[int, int] | None = None
    for trade_date in trading_dates:
        month = (trade_date.year, trade_date.month)
        if month != previous_month:
            selected.append(trade_date)
            previous_month = month
    return selected


def _tradable(bar: PriceBar) -> bool:
    prices = (bar.open_price, bar.high_price, bar.low_price, bar.close_price)
    if any(value is None for value in prices) or bar.volume is None:
        return False
    open_price, high, low, close = (Decimal(value) for value in prices)  # type: ignore[arg-type]
    if close <= 0 or bar.volume < 0:
        return False
    if open_price <= 0 or high <= 0 or low <= 0:
        return False
    return not (
        high < low
        or high < open_price
        or high < close
        or low > open_price
        or low > close
    )


def select_momentum_targets(
    bars_by_stock: dict[str, list[PriceBar]],
    as_of: date,
) -> dict[str, Decimal]:
    """미래 행을 보지 않고 실제 모델과 같은 필터·120일 점수로 상위 5개를 고른다."""

    candidates: list[tuple[float, Decimal, str]] = []
    for stock_code, all_bars in bars_by_stock.items():
        history = [bar for bar in all_bars if bar.trade_date <= as_of]
        if not history or history[-1].trade_date != as_of:
            continue
        current = history[-1]
        if not _tradable(current):
            continue
        if current.close_price is None or current.close_price < Decimal("1000"):
            continue
        if current.market_cap is None or current.market_cap <= 0:
            continue
        if len(history) < 121:
            continue

        recent_20 = history[-20:]
        recent_61 = history[-61:]
        if len(recent_20) < 20 or len(recent_61) < 61:
            continue
        if any(bar.trading_value is None for bar in recent_20):
            continue
        if any(bar.volume is None for bar in recent_20):
            continue
        trading_value_sma = sum(
            (Decimal(bar.trading_value) for bar in recent_20), Decimal("0")
        ) / Decimal("20")
        volume_sma = sum((Decimal(bar.volume) for bar in recent_20), Decimal("0")) / Decimal("20")
        if trading_value_sma < 0 or volume_sma <= 0:
            continue
        volume_ratio = Decimal(current.volume) / volume_sma
        if volume_ratio > Decimal("10"):
            continue

        closes = [Decimal(bar.close_price) for bar in recent_61 if bar.close_price is not None]
        if len(closes) != 61 or any(value <= 0 for value in closes):
            continue
        returns = [float(current_close / previous_close - 1) for previous_close, current_close in zip(closes, closes[1:])]
        volatility = stdev(returns) * math.sqrt(252)
        if volatility > 1.0:
            continue

        base = history[-121].close_price
        if base is None or base <= 0:
            continue
        momentum = float(Decimal(current.close_price) / Decimal(base) - 1)
        # 동일 점수면 실제 ranker의 사전 정렬과 같이 시가총액 내림차순, 코드 순이다.
        candidates.append((momentum, Decimal(current.market_cap), stock_code))

    selected = sorted(candidates, key=lambda item: (-item[0], -item[1], item[2]))[:TOP_N]
    if len(selected) < TOP_N:
        raise RuntimeError(f"{as_of} 모멘텀 모델 적격 종목이 부족합니다: {len(selected)}")
    return {stock_code: TARGET_WEIGHT for _, _, stock_code in selected}
