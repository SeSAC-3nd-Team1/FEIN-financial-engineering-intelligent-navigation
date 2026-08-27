"""시점별 실제 KRX 가격과 공시 가능 재무정보를 사용하는 전략 백테스트 엔진."""

from collections import defaultdict
from datetime import date, timedelta
import math
from statistics import fmean, pstdev

from app.core.errors import NotFoundError, ServiceError
from app.repositories.backtest import (
    BacktestRepository,
    IndexPricePoint,
    PointInTimeFinancial,
    StockPricePoint,
)
from app.schemas.api import BacktestAvailableRangeResponse, BacktestRunRequest, BacktestRunResponse


LOOKBACK_DAYS = 260
LOW_VOL_WINDOW = 60
MOMENTUM_WINDOW = 126
MIN_LOW_VOL_OBSERVATIONS = LOW_VOL_WINDOW
MIN_MOMENTUM_OBSERVATIONS = MOMENTUM_WINDOW
PORTFOLIO_SIZE = 10


def _round(value: float, digits: int = 4) -> float:
    return round(value, digits)


def calculate_metrics(values: list[float], dates: list[date]) -> dict[str, float | None]:
    if len(values) < 2 or len(values) != len(dates) or values[0] <= 0:
        raise ValueError("at least two aligned positive portfolio values are required")
    daily_returns = [current / previous - 1 for previous, current in zip(values, values[1:]) if previous > 0]
    cumulative = values[-1] / values[0] - 1
    years = max((dates[-1] - dates[0]).days / 365.25, 1 / 365.25)
    cagr = (values[-1] / values[0]) ** (1 / years) - 1 if values[-1] > 0 else -1.0
    peak = values[0]
    mdd = 0.0
    for value in values:
        peak = max(peak, value)
        mdd = min(mdd, value / peak - 1)
    volatility = pstdev(daily_returns) * math.sqrt(252) if len(daily_returns) >= 2 else 0.0
    sharpe = None if volatility == 0 else fmean(daily_returns) / pstdev(daily_returns) * math.sqrt(252)
    return {
        "cumulative_return": _round(cumulative * 100),
        "cagr": _round(cagr * 100),
        "mdd": _round(mdd * 100),
        "volatility": _round(volatility * 100),
        "sharpe": _round(sharpe) if sharpe is not None else None,
    }


class BacktestService:
    def __init__(self, repository: BacktestRepository) -> None:
        self.repository = repository

    def available_range(self) -> BacktestAvailableRangeResponse:
        stock_min, stock_max, index_min, index_max = self.repository.available_dates(min_stocks=PORTFOLIO_SIZE)
        if None in {stock_min, stock_max, index_min, index_max}:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "백테스트 기간 정보를 찾을 수 없습니다.")
        min_date = max(stock_min + timedelta(days=LOOKBACK_DAYS), index_min)
        max_date = min(stock_max, index_max)
        if min_date >= max_date:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "백테스트 가능한 공통 기간이 없습니다.")
        return BacktestAvailableRangeResponse.model_validate({"minDate": min_date, "maxDate": max_date})

    def run(self, request: BacktestRunRequest) -> BacktestRunResponse:
        strategy = self.repository.strategy(request.strategy_id)
        if strategy is None:
            raise NotFoundError("STRATEGY_NOT_FOUND", "활성 투자 전략을 찾을 수 없습니다.")
        factor = str((strategy.rule_config or {}).get("factor", ""))
        if factor not in {"low_volatility", "momentum", "value"}:
            raise ServiceError("BACKTEST_STRATEGY_UNAVAILABLE", "지원하지 않는 전략 규칙입니다.", 422)

        universe = self.repository.universe_codes(request.start_date)
        if len(universe) < PORTFOLIO_SIZE:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "백테스트 universe 데이터가 부족합니다.")
        warmup_start = request.start_date - timedelta(days=LOOKBACK_DAYS)
        price_points = self.repository.stock_prices(universe, warmup_start, request.end_date)
        benchmark = self.repository.kospi_prices(request.start_date, request.end_date)
        if len(benchmark) < 2:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "KOSPI 기준지수 데이터가 부족합니다.")

        financial_points: list[PointInTimeFinancial] = []
        if factor == "value":
            financial_points = self.repository.point_in_time_financials(universe, request.end_date)
            if len({point.stock_code for point in financial_points}) < PORTFOLIO_SIZE:
                raise NotFoundError(
                    "BACKTEST_DATA_UNAVAILABLE",
                    "가치 전략에 필요한 공시 시점 기준 재무 데이터가 부족합니다.",
                )

        prices = self._price_map(price_points)
        market_caps = self._market_cap_map(price_points)
        financials = self._financial_map(financial_points)
        corporate_actions = self._corporate_action_dates(price_points)
        dates = [point.trade_date for point in benchmark]
        strategy_values = self._simulate(
            factor,
            prices,
            dates,
            corporate_actions,
            market_caps=market_caps,
            financials=financials,
            rebalance_cycle=strategy.rebalance_cycle,
        )
        benchmark_values = self._benchmark_values(benchmark)
        metrics = calculate_metrics(strategy_values, dates)
        benchmark_metrics = calculate_metrics(benchmark_values, dates)
        series = [
            {
                "t": trade_date,
                "strategy": _round((strategy_value / strategy_values[0] - 1) * 100),
                "benchmark": _round((benchmark_value / benchmark_values[0] - 1) * 100),
            }
            for trade_date, strategy_value, benchmark_value in zip(dates, strategy_values, benchmark_values)
        ]
        return BacktestRunResponse.model_validate({
            "strategy_id": strategy.id,
            "strategy_name": strategy.name,
            "period": {
                "id": request.period_id,
                "label": request.period_label,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "description": request.period_description,
            },
            "series": series,
            "metrics": metrics,
            "benchmark_name": "KOSPI",
            "benchmark_metrics": {
                "cumulative_return": benchmark_metrics["cumulative_return"],
                "mdd": benchmark_metrics["mdd"],
            },
        })

    @staticmethod
    def _price_map(points: list[StockPricePoint]) -> dict[str, dict[date, float]]:
        prices: dict[str, dict[date, float]] = defaultdict(dict)
        for point in points:
            close = float(point.close)
            if close > 0:
                prices[point.stock_code][point.trade_date] = close
        return prices

    @staticmethod
    def _market_cap_map(points: list[StockPricePoint]) -> dict[str, dict[date, float]]:
        market_caps: dict[str, dict[date, float]] = defaultdict(dict)
        for point in points:
            if point.market_cap is None:
                continue
            market_cap = float(point.market_cap)
            if market_cap > 0:
                market_caps[point.stock_code][point.trade_date] = market_cap
        return market_caps

    @staticmethod
    def _financial_map(points: list[PointInTimeFinancial]) -> dict[str, list[PointInTimeFinancial]]:
        financials: dict[str, list[PointInTimeFinancial]] = defaultdict(list)
        for point in sorted(points, key=lambda item: (item.stock_code, item.available_at)):
            financials[point.stock_code].append(point)
        return financials

    @staticmethod
    def _corporate_action_dates(points: list[StockPricePoint]) -> set[tuple[str, date]]:
        actions: set[tuple[str, date]] = set()
        previous_shares: dict[str, int] = {}
        for point in sorted(points, key=lambda item: (item.stock_code, item.trade_date)):
            shares = point.listed_shares
            if shares is None or shares <= 0:
                continue
            previous = previous_shares.get(point.stock_code)
            if previous is not None and shares != previous:
                actions.add((point.stock_code, point.trade_date))
            previous_shares[point.stock_code] = shares
        return actions

    def _simulate(
        self,
        factor: str,
        prices: dict[str, dict[date, float]],
        dates: list[date],
        corporate_actions: set[tuple[str, date]] | None = None,
        *,
        market_caps: dict[str, dict[date, float]] | None = None,
        financials: dict[str, list[PointInTimeFinancial]] | None = None,
        rebalance_cycle: str = "MONTHLY",
    ) -> list[float]:
        action_dates = corporate_actions or set()
        cap_history = market_caps or {}
        financial_history = financials or {}
        holdings = self._select(
            factor,
            prices,
            dates[0],
            action_dates,
            market_caps=cap_history,
            financials=financial_history,
        )
        if len(holdings) < PORTFOLIO_SIZE:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "전략 산출에 필요한 과거 데이터가 부족합니다.")
        allocations = {code: 1.0 / len(holdings) for code in holdings}
        values = [1.0]
        last_observed = {
            code: self._last_observed_price(prices.get(code, {}), dates[0])
            for code in holdings
        }
        previous_bucket = self._rebalance_bucket(dates[0], rebalance_cycle)

        for trade_date in dates[1:]:
            for code in list(allocations):
                current_close = prices.get(code, {}).get(trade_date)
                previous_close = last_observed.get(code)
                if current_close:
                    if previous_close and (code, trade_date) not in action_dates:
                        allocations[code] *= current_close / previous_close
                    last_observed[code] = current_close
            total = sum(allocations.values())
            values.append(total)
            bucket = self._rebalance_bucket(trade_date, rebalance_cycle)
            if bucket != previous_bucket:
                selected = self._select(
                    factor,
                    prices,
                    trade_date,
                    action_dates,
                    market_caps=cap_history,
                    financials=financial_history,
                )
                if len(selected) >= PORTFOLIO_SIZE:
                    allocations = {code: total / len(selected) for code in selected}
                    last_observed = {
                        code: self._last_observed_price(prices.get(code, {}), trade_date)
                        for code in selected
                    }
                previous_bucket = bucket
        return values

    @staticmethod
    def _rebalance_bucket(trade_date: date, rebalance_cycle: str) -> tuple[int, int]:
        if rebalance_cycle == "QUARTERLY":
            return trade_date.year, (trade_date.month - 1) // 3 + 1
        return trade_date.year, trade_date.month

    @staticmethod
    def _last_observed_price(history: dict[date, float], as_of: date) -> float | None:
        return next((close for trade_date, close in sorted(history.items(), reverse=True) if trade_date <= as_of), None)

    @staticmethod
    def _select(
        factor: str,
        prices: dict[str, dict[date, float]],
        as_of: date,
        corporate_actions: set[tuple[str, date]] | None = None,
        *,
        market_caps: dict[str, dict[date, float]] | None = None,
        financials: dict[str, list[PointInTimeFinancial]] | None = None,
    ) -> list[str]:
        action_dates = corporate_actions or set()
        cap_history = market_caps or {}
        financial_history = financials or {}
        scores: list[tuple[float, str]] = []
        for code, history in prices.items():
            if as_of not in history:
                continue

            if factor == "value":
                market_cap = cap_history.get(code, {}).get(as_of)
                if market_cap is None or market_cap <= 0:
                    continue
                latest_financial = next(
                    (
                        point
                        for point in reversed(financial_history.get(code, []))
                        if point.available_at <= as_of
                    ),
                    None,
                )
                if latest_financial is None or latest_financial.total_equity <= 0:
                    continue
                book_to_price = float(latest_financial.total_equity) / market_cap
                scores.append((-book_to_price, code))
                continue

            observations = [(trade_date, close) for trade_date, close in sorted(history.items()) if trade_date <= as_of]
            if factor == "low_volatility":
                recent = observations[-(LOW_VOL_WINDOW + 1):]
                returns = [
                    current[1] / previous[1] - 1
                    for previous, current in zip(recent, recent[1:])
                    if (code, current[0]) not in action_dates
                ]
                if len(returns) < MIN_LOW_VOL_OBSERVATIONS:
                    continue
                scores.append((pstdev(returns), code))
            elif factor == "momentum":
                recent = observations[-(MOMENTUM_WINDOW + 1):]
                if (
                    len(recent) - 1 < MIN_MOMENTUM_OBSERVATIONS
                    or recent[0][1] <= 0
                    or any((code, trade_date) in action_dates for trade_date, _ in recent[1:])
                ):
                    continue
                scores.append((-(recent[-1][1] / recent[0][1] - 1), code))
        return [code for _, code in sorted(scores)[:PORTFOLIO_SIZE]]

    @staticmethod
    def _benchmark_values(points: list[IndexPricePoint]) -> list[float]:
        first = float(points[0].close)
        if first <= 0:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "KOSPI 기준지수 값이 올바르지 않습니다.")
        return [float(point.close) / first for point in points]
