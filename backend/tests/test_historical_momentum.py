from datetime import date, timedelta
from decimal import Decimal

from scripts.historical_momentum import (
    PriceBar,
    monthly_signal_dates,
    select_momentum_targets,
)


def bars(stock_code: str, growth: Decimal, days: int = 130) -> list[PriceBar]:
    result = []
    for index in range(days):
        close = Decimal("2000") + growth * index
        result.append(
            PriceBar(
                stock_code=stock_code,
                trade_date=date(2026, 1, 1) + timedelta(days=index),
                open_price=close,
                high_price=close + Decimal("10"),
                low_price=close - Decimal("10"),
                close_price=close,
                volume=1000,
                trading_value=close * 1000,
                market_cap=Decimal("1000000000") + index,
            )
        )
    return result


def test_historical_momentum_selects_top_five_without_future_rows() -> None:
    history = {
        f"00000{index}": bars(f"00000{index}", Decimal(index))
        for index in range(1, 7)
    }
    as_of = date(2026, 1, 1) + timedelta(days=120)
    selected = select_momentum_targets(history, as_of)

    assert list(selected) == ["000006", "000005", "000004", "000003", "000002"]
    assert sum(selected.values(), Decimal("0")) == Decimal("0.95")

    # 기준일 이후 가격을 극단적으로 바꿔도 과거 선택 결과는 달라지지 않는다.
    future = history["000001"][-1]
    history["000001"][-1] = PriceBar(
        **{**future.__dict__, "close_price": Decimal("999999999")}
    )
    assert select_momentum_targets(history, as_of) == selected


def test_historical_momentum_excludes_non_tradable_current_bar() -> None:
    history = {
        f"00000{index}": bars(f"00000{index}", Decimal(index))
        for index in range(1, 7)
    }
    as_of = history["000006"][120].trade_date
    stopped = history["000006"][120]
    history["000006"][120] = PriceBar(
        **{
            **stopped.__dict__,
            "open_price": Decimal("0"),
            "high_price": Decimal("0"),
            "low_price": Decimal("0"),
        }
    )

    assert "000006" not in select_momentum_targets(history, as_of)


def test_monthly_signal_dates_uses_first_available_date_of_each_month() -> None:
    dates = [
        date(2026, 1, 30),
        date(2026, 2, 2),
        date(2026, 2, 3),
        date(2026, 3, 2),
    ]

    assert monthly_signal_dates(dates) == [dates[0], dates[1], dates[3]]
