"""실제 시계열 기반 백테스트 지표·전략·KOSPI 비교 규칙을 검증한다."""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.errors import ServiceError
from app.repositories.backtest import IndexPricePoint, StockPricePoint
from app.schemas.api import BacktestRunRequest
from app.services.backtest import BacktestService, calculate_metrics


class FakeRepository:
    def __init__(self, factor: str = "momentum") -> None:
        self.factor = factor
        self.start = date(2026, 1, 1)
        self.codes = [f"{index:06d}" for index in range(12)]

    def strategy(self, strategy_id: str):
        if strategy_id not in {"low", "value", "momentum"}:
            return None
        return SimpleNamespace(id=strategy_id, name="테스트 전략", rule_config={"factor": self.factor})

    def universe_codes(self, _as_of: date, *, limit: int = 100) -> list[str]:
        return self.codes[:limit]

    def stock_prices(self, stock_codes: list[str], _start_date: date, end_date: date) -> list[StockPricePoint]:
        first = self.start - timedelta(days=150)
        points: list[StockPricePoint] = []
        day = first
        offset = 0
        while day <= end_date:
            for index, code in enumerate(stock_codes):
                price = Decimal("100") * (Decimal("1") + Decimal("0.0002") * (index + 1)) ** offset
                points.append(StockPricePoint(code, day, price))
            day += timedelta(days=1)
            offset += 1
        return points

    def kospi_prices(self, start_date: date, end_date: date) -> list[IndexPricePoint]:
        points: list[IndexPricePoint] = []
        current = start_date
        value = Decimal("100")
        while current <= end_date:
            points.append(IndexPricePoint(current, value))
            current += timedelta(days=1)
            value += Decimal("1")
        return points


def request(strategy_id: str = "momentum") -> BacktestRunRequest:
    return BacktestRunRequest.model_validate({
        "strategyId": strategy_id,
        "periodId": "custom",
        "periodLabel": "직접 설정",
        "periodDescription": "",
        "startDate": "2026-01-01",
        "endDate": "2026-01-10",
    })


def test_metrics_calculate_return_cagr_mdd_volatility_and_sharpe() -> None:
    metrics = calculate_metrics(
        [1.0, 1.1, 0.99, 1.2],
        [date(2025, 1, 1), date(2025, 5, 1), date(2025, 9, 1), date(2026, 1, 1)],
    )

    assert metrics["cumulative_return"] == 20.0
    assert metrics["cagr"] == pytest.approx(20.0, abs=0.1)
    assert metrics["mdd"] == -10.0
    assert metrics["volatility"] > 0
    assert metrics["sharpe"] is not None


def test_backtest_uses_historical_strategy_prices_and_real_kospi() -> None:
    result = BacktestService(FakeRepository()).run(request())

    assert result.strategy_id == "momentum"
    assert len(result.series) == 10
    assert result.series[0].strategy == 0
    assert result.series[0].benchmark == 0
    assert result.series[-1].strategy > 0
    assert result.benchmark_metrics.cumulative_return == 9.0
    assert result.metrics.cumulative_return > 0
    assert result.model_dump(by_alias=True)["strategyId"] == "momentum"


def test_factor_selection_does_not_use_prices_after_rebalance_date() -> None:
    as_of = date(2026, 1, 1)
    history = {
        "000001": {as_of - timedelta(days=1): 100.0, as_of: 101.0, as_of + timedelta(days=1): 10_000.0},
    }
    for index in range(2, 12):
        history[f"{index:06d}"] = {
            as_of - timedelta(days=1): 100.0,
            as_of: 100.0 + index,
        }

    # 관측치가 짧아 실제 momentum 후보는 없지만 미래 급등값을 넣어도 선택 결과에 들어가면 안 된다.
    assert BacktestService._select("momentum", history, as_of) == []


def test_value_strategy_is_unavailable_without_point_in_time_financials() -> None:
    with pytest.raises(ServiceError) as exc_info:
        BacktestService(FakeRepository(factor="value")).run(request("value"))

    assert exc_info.value.code == "BACKTEST_STRATEGY_UNAVAILABLE"
    assert exc_info.value.status_code == 422
