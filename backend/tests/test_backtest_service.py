"""실제 시계열 기반 백테스트 지표·전략·KOSPI·PIT 가치 규칙을 검증한다."""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.repositories.backtest import (
    IndexPricePoint,
    PointInTimeFinancial,
    StockPricePoint,
    disclosure_matches_financial_period,
    financial_period_end,
)
from app.schemas.api import BacktestRunRequest
from app.services.backtest import BacktestService, calculate_metrics


class FakeRepository:
    def __init__(self, factor: str = "momentum") -> None:
        self.factor = factor
        self.start = date(2026, 1, 1)
        self.codes = [f"{index:06d}" for index in range(25)]

    def strategy(self, strategy_id: str):
        if strategy_id not in {"low", "value", "momentum"}:
            return None
        return SimpleNamespace(
            id=strategy_id,
            name="테스트 전략",
            rule_config={"factor": self.factor},
            rebalance_cycle="QUARTERLY" if self.factor == "value" else "MONTHLY",
        )

    def universe_codes(self, _as_of: date, *, limit: int = 100) -> list[str]:
        return self.codes[:limit]

    def stock_codes(self, _start_date: date, _end_date: date) -> list[str]:
        return self.codes

    def available_dates(self, *, min_stocks: int):
        assert min_stocks == 10
        return date(2020, 1, 1), date(2026, 8, 20), date(2020, 3, 1), date(2026, 8, 18)

    def stock_prices(self, stock_codes: list[str], _start_date: date, end_date: date) -> list[StockPricePoint]:
        # v2 needs 12M skip-1M plus three years of weekly volatility history.
        first = self.start - timedelta(days=1_200)
        points: list[StockPricePoint] = []
        day = first
        offset = 0
        while day <= end_date:
            for index, code in enumerate(stock_codes):
                price = Decimal("100") * (Decimal("1") + Decimal("0.0002") * (index + 1)) ** offset
                points.append(
                    StockPricePoint(
                        code,
                        day,
                        price,
                        listed_shares=1_000_000 + index,
                        market_cap=Decimal("1000000") + Decimal(index * 10000),
                    )
                )
            day += timedelta(days=1)
            offset += 1
        return points

    def point_in_time_financials(
        self,
        stock_codes: list[str],
        _end_date: date,
    ) -> list[PointInTimeFinancial]:
        return [
            PointInTimeFinancial(
                stock_code=code,
                available_at=self.start - timedelta(days=30),
                period_end=date(2025, 9, 30),
                business_year="2025",
                report_code="11014",
                fs_div="CFS",
                total_equity=Decimal("100000") + Decimal(index * 10000),
                net_income=Decimal("10000") + Decimal(index * 1000),
            )
            for index, code in enumerate(stock_codes)
        ]

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


def test_available_range_uses_warmup_and_common_stock_index_end_date() -> None:
    result = BacktestService(FakeRepository()).available_range()

    assert result.min_date == date(2020, 9, 17)
    assert result.max_date == date(2026, 8, 18)


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


def test_value_backtest_uses_point_in_time_financials() -> None:
    result = BacktestService(FakeRepository(factor="value")).run(request("value"))

    assert result.strategy_id == "value"
    assert len(result.series) == 10
    assert result.metrics.cumulative_return > 0


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

    assert BacktestService._select("momentum", history, as_of) == []


def test_value_selection_never_uses_financials_before_disclosure_date() -> None:
    as_of = date(2026, 1, 1)
    prices = {f"{index:06d}": {as_of: 100.0} for index in range(11)}
    market_caps = {f"{index:06d}": {as_of: 1000.0} for index in range(11)}
    financials: dict[str, list[PointInTimeFinancial]] = {}
    for index in range(10):
        code = f"{index:06d}"
        financials[code] = [
            PointInTimeFinancial(
                stock_code=code,
                available_at=as_of - timedelta(days=1),
                period_end=date(2025, 9, 30),
                business_year="2025",
                report_code="11014",
                fs_div="CFS",
                total_equity=Decimal(100 + index),
            )
        ]
    financials["000010"] = [
        PointInTimeFinancial(
            stock_code="000010",
            available_at=as_of + timedelta(days=1),
            period_end=date(2025, 9, 30),
            business_year="2025",
            report_code="11014",
            fs_div="CFS",
            total_equity=Decimal("999999"),
        )
    ]

    selected = BacktestService._select(
        "value",
        prices,
        as_of,
        market_caps=market_caps,
        financials=financials,
    )

    assert len(selected) == 10
    assert "000010" not in selected


def test_value_selection_prefers_latest_period_over_late_old_period_correction() -> None:
    as_of = date(2026, 1, 1)
    prices = {f"{index:06d}": {as_of: 100.0} for index in range(11)}
    market_caps = {f"{index:06d}": {as_of: 1000.0} for index in range(11)}
    financials: dict[str, list[PointInTimeFinancial]] = {}
    for index in range(10):
        code = f"{index:06d}"
        financials[code] = [
            PointInTimeFinancial(
                stock_code=code,
                available_at=date(2025, 11, 15),
                period_end=date(2025, 9, 30),
                business_year="2025",
                report_code="11014",
                fs_div="CFS",
                total_equity=Decimal(100 + index),
            )
        ]

    # 2024 Q1 정정공시가 더 늦게 접수됐어도, 2026-01-01에 이미 공개된 2025 Q3보다
    # 최신 재무정보로 취급하면 안 된다. 최신 period의 B/P가 낮으므로 이 종목은 제외돼야 한다.
    financials["000010"] = [
        PointInTimeFinancial(
            stock_code="000010",
            available_at=date(2025, 11, 15),
            period_end=date(2025, 9, 30),
            business_year="2025",
            report_code="11014",
            fs_div="CFS",
            total_equity=Decimal("1"),
        ),
        PointInTimeFinancial(
            stock_code="000010",
            available_at=date(2025, 12, 20),
            period_end=date(2024, 3, 31),
            business_year="2024",
            report_code="11013",
            fs_div="CFS",
            total_equity=Decimal("999999"),
        ),
    ]

    selected = BacktestService._select(
        "value",
        prices,
        as_of,
        market_caps=market_caps,
        financials=financials,
    )

    assert len(selected) == 10
    assert "000010" not in selected


def test_financial_period_end_supports_quarter_and_non_december_fiscal_year() -> None:
    assert financial_period_end("2024", "11013", "12") == date(2024, 3, 31)
    assert financial_period_end("2024", "11011", "12") == date(2024, 12, 31)
    assert financial_period_end("2024", "11013", "03") == date(2023, 6, 30)


def test_financial_period_end_rejects_missing_accounting_month() -> None:
    assert financial_period_end("2024", "11011", None) is None
    assert financial_period_end("2024", "11011", "") is None


def test_disclosure_period_match_rejects_other_quarter() -> None:
    q1_end = date(2024, 3, 31)

    assert disclosure_matches_financial_period("분기보고서 (2024.03)", "11013", q1_end)
    assert not disclosure_matches_financial_period("분기보고서 (2024.09)", "11013", q1_end)
    assert not disclosure_matches_financial_period("반기보고서 (2024.06)", "11013", q1_end)


def test_suspended_holding_applies_full_return_when_trading_resumes() -> None:
    monday = date(2026, 1, 5)
    thursday = monday + timedelta(days=3)
    prices: dict[str, dict[date, float]] = {}
    for index in range(10):
        code = f"{index:06d}"
        history = {monday - timedelta(days=offset): 100.0 for offset in range(61)}
        history[thursday] = 80.0
        prices[code] = history

    values = BacktestService(SimpleNamespace())._simulate(
        "low_volatility",
        prices,
        [monday, monday + timedelta(days=1), monday + timedelta(days=2), thursday],
    )

    assert values == pytest.approx([1.0, 1.0, 1.0, 0.8])


def test_suspended_stock_is_not_selected_for_new_position() -> None:
    rebalance_date = date(2026, 1, 31)
    suspended_code = "000000"
    prices: dict[str, dict[date, float]] = {}
    for index in range(11):
        code = f"{index:06d}"
        first_offset = 1 if code == suspended_code else 0
        prices[code] = {
            rebalance_date - timedelta(days=offset): 100.0
            for offset in range(first_offset, first_offset + 61)
        }

    selected = BacktestService._select("low_volatility", prices, rebalance_date)

    assert len(selected) == 10
    assert suspended_code not in selected


def test_unadjusted_corporate_action_resets_price_without_false_return() -> None:
    start = date(2026, 1, 5)
    split_day = start + timedelta(days=1)
    prices: dict[str, dict[date, float]] = {}
    for index in range(10):
        code = f"{index:06d}"
        history = {start - timedelta(days=offset): 100.0 for offset in range(61)}
        history[split_day] = 50.0
        history[split_day + timedelta(days=1)] = 55.0
        prices[code] = history

    actions = {(code, split_day) for code in prices}
    values = BacktestService(SimpleNamespace())._simulate(
        "low_volatility", prices, [start, split_day, split_day + timedelta(days=1)], actions,
    )

    assert values == pytest.approx([1.0, 1.0, 1.1])
