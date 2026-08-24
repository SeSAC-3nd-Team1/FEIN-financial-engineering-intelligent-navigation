"""시점별 실제 KRX 가격만 사용하는 전략 백테스트 엔진."""

from collections import defaultdict
from datetime import date, timedelta
import math
from statistics import fmean, pstdev

from app.core.errors import NotFoundError, ServiceError
from app.repositories.backtest import BacktestRepository, IndexPricePoint, StockPricePoint
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
        if factor == "value":
            raise ServiceError(
                "BACKTEST_STRATEGY_UNAVAILABLE",
                "가치 전략은 공시 가능일 기준 재무 데이터가 준비된 뒤 제공됩니다.",
                422,
            )
        if factor not in {"low_volatility", "momentum"}:
            raise ServiceError("BACKTEST_STRATEGY_UNAVAILABLE", "지원하지 않는 전략 규칙입니다.", 422)

        universe = self.repository.universe_codes(request.start_date)
        if len(universe) < PORTFOLIO_SIZE:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "백테스트 universe 데이터가 부족합니다.")
        warmup_start = request.start_date - timedelta(days=LOOKBACK_DAYS)
        price_points = self.repository.stock_prices(universe, warmup_start, request.end_date)
        benchmark = self.repository.kospi_prices(request.start_date, request.end_date)
        if len(benchmark) < 2:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "KOSPI 기준지수 데이터가 부족합니다.")

        prices = self._price_map(price_points)
        corporate_actions = self._corporate_action_dates(price_points)
        dates = [point.trade_date for point in benchmark]
        strategy_values = self._simulate(factor, prices, dates, corporate_actions)
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
    ) -> list[float]:
        action_dates = corporate_actions or set()
        holdings = self._select(factor, prices, dates[0], action_dates)
        if len(holdings) < PORTFOLIO_SIZE:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "전략 산출에 필요한 과거 시세가 부족합니다.")
        allocations = {code: 1.0 / len(holdings) for code in holdings}
        values = [1.0]
        last_observed = {
            code: self._last_observed_price(prices.get(code, {}), dates[0])
            for code in holdings
        }
        previous_month = (dates[0].year, dates[0].month)

        for trade_date in dates[1:]:
            for code in list(allocations):
                current_close = prices.get(code, {}).get(trade_date)
                previous_close = last_observed.get(code)
                if current_close:
                    # 원천 KRX 종가는 수정주가가 아니므로 상장주식수 변동일은
                    # 수익률을 계산하지 않고 새 기준가로만 연결해 분할·병합 왜곡을 막는다.
                    if previous_close and (code, trade_date) not in action_dates:
                        allocations[code] *= current_close / previous_close
                    last_observed[code] = current_close
            total = sum(allocations.values())
            values.append(total)
            month = (trade_date.year, trade_date.month)
            if month != previous_month:
                selected = self._select(factor, prices, trade_date, action_dates)
                if len(selected) >= PORTFOLIO_SIZE:
                    allocations = {code: total / len(selected) for code in selected}
                    last_observed = {
                        code: self._last_observed_price(prices.get(code, {}), trade_date)
                        for code in selected
                    }
                previous_month = month
        return values

    @staticmethod
    def _last_observed_price(history: dict[date, float], as_of: date) -> float | None:
        return next((close for trade_date, close in sorted(history.items(), reverse=True) if trade_date <= as_of), None)

    @staticmethod
    def _select(
        factor: str,
        prices: dict[str, dict[date, float]],
        as_of: date,
        corporate_actions: set[tuple[str, date]] | None = None,
    ) -> list[str]:
        action_dates = corporate_actions or set()
        scores: list[tuple[float, str]] = []
        for code, history in prices.items():
            # 신규 편입은 리밸런싱일에 실제 매수 가능한 종목으로 제한한다.
            # 기존 보유종목의 거래정지 평가는 _simulate()의 last_observed가 담당한다.
            if as_of not in history:
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
            else:
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
