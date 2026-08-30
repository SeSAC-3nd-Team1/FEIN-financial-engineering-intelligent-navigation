"""시점별 실제 KRX 가격과 공시 가능 재무정보를 사용하는 전략 백테스트 엔진."""

from collections import defaultdict
from itertools import chain, groupby
from datetime import date, timedelta
import gc
import math
from statistics import fmean, pstdev

import pandas as pd
from shared.momentum_features import add_momentum_features

# Kept in the AI package on purpose.  The service must consume exactly the
# factor implementation which produces the live recommendation artifact.
from inference.risk_adjusted_recommendation_snapshot import _capped_score_market_cap_weights
from models.risk_adjusted_momentum import RiskAdjustedMomentumModel
from risk import apply_stock_risk_filter

from app.core.errors import NotFoundError, ServiceError
from app.repositories.backtest import (
    BacktestRepository,
    IndexPricePoint,
    PointInTimeFinancial,
    StockPricePoint,
)
from app.schemas.api import BacktestAvailableRangeResponse, BacktestRunRequest, BacktestRunResponse


# v2 needs 273 trading days for the 12M/skip-1M return and 156 completed
# weekly volatility observations.  1,500 calendar days leaves enough room for
# weekends, holidays, and sparse listings in the real repository.
V2_LOOKBACK_DAYS = 1500
LOOKBACK_DAYS = 260
LOW_VOL_WINDOW = 60
MOMENTUM_WINDOW = 126  # legacy baseline helper; service momentum uses v2 below.
MIN_LOW_VOL_OBSERVATIONS = LOW_VOL_WINDOW
MIN_MOMENTUM_OBSERVATIONS = MOMENTUM_WINDOW
PORTFOLIO_SIZE = 10
V2_FEATURE_COLUMNS = [
    "trade_date",
    "stock_code",
    "market_cap",
    "risk_adjusted_momentum_6m",
    "risk_adjusted_momentum_12m",
    "v2_history_ready",
    "corporate_action_safe",
    "corporate_action_event_safe",
    "is_tradable",
    "risk_eligible",
    "point_in_time_adjusted_close",
]


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

    def available_range(self, strategy_id: str | None = None) -> BacktestAvailableRangeResponse:
        stock_min, stock_max, index_min, index_max = self.repository.available_dates(min_stocks=PORTFOLIO_SIZE)
        if None in {stock_min, stock_max, index_min, index_max}:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "백테스트 기간 정보를 찾을 수 없습니다.")
        lookback_days = V2_LOOKBACK_DAYS if strategy_id == "momentum" else LOOKBACK_DAYS
        min_date = max(stock_min + timedelta(days=lookback_days), index_min)
        max_date = min(stock_max, index_max)
        if min_date >= max_date:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "백테스트 가능한 공통 기간이 없습니다.")
        return BacktestAvailableRangeResponse.model_validate({"minDate": min_date, "maxDate": max_date})

    def run(self, request: BacktestRunRequest) -> BacktestRunResponse:
        if request.period_id == "custom":
            raise ServiceError(
                "BACKTEST_CUSTOM_PERIOD_DISABLED",
                "MVP에서는 제공되는 백테스트 기간만 선택할 수 있습니다.",
                422,
            )
        strategy = self.repository.strategy(request.strategy_id)
        if strategy is None:
            raise NotFoundError("STRATEGY_NOT_FOUND", "활성 투자 전략을 찾을 수 없습니다.")
        factor = str((strategy.rule_config or {}).get("factor", ""))
        if factor not in {"low_volatility", "momentum", "value"}:
            raise ServiceError("BACKTEST_STRATEGY_UNAVAILABLE", "지원하지 않는 전략 규칙입니다.", 422)

        lookback_days = V2_LOOKBACK_DAYS if factor == "momentum" else LOOKBACK_DAYS
        if factor == "momentum":
            # Keep every code observed in the period so rank() can rebuild the
            # top-100 investable universe at each point in time.
            universe = self.repository.stock_codes(
                request.start_date - timedelta(days=lookback_days), request.end_date
            )
        else:
            universe = self.repository.universe_codes(request.start_date)
        if len(universe) < PORTFOLIO_SIZE:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "백테스트 universe 데이터가 부족합니다.")
        warmup_start = request.start_date - timedelta(days=lookback_days)
        price_points = (
            self.repository.stock_price_stream(universe, warmup_start, request.end_date)
            if factor == "momentum" and hasattr(self.repository, "stock_price_stream")
            else self.repository.stock_prices(universe, warmup_start, request.end_date)
        )
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

        dates = [point.trade_date for point in benchmark]
        if factor == "momentum":
            # stock_price_stream is a single-pass iterator.  Do not consume it
            # while building legacy maps before the v2 simulator reads it.
            strategy_values = self._simulate_risk_adjusted_momentum_v2(price_points, dates)
        else:
            prices = self._price_map(price_points)
            market_caps = self._market_cap_map(price_points)
            financials = self._financial_map(financial_points)
            corporate_actions = self._corporate_action_dates(price_points)
            strategy_values = self._simulate(
                factor, prices, dates, corporate_actions,
                market_caps=market_caps, financials=financials,
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
        for point in sorted(points, key=lambda item: (item.stock_code, item.period_end, item.available_at)):
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
    def _simulate_risk_adjusted_momentum_v2(
        points: list[StockPricePoint], dates: list[date]
    ) -> list[float]:
        """Run quarterly v2 targets with drift, using the AI factor source of truth.

        Targets are decided with rows through the decision close and become active
        on the next available benchmark trading day.  Unsafe/missing observations
        fail closed instead of inventing a return.
        """
        model = RiskAdjustedMomentumModel()
        features = BacktestService._build_v2_features(points, model)
        if features.empty:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "모멘텀 v2 가격 데이터가 부족합니다.")
        price_matrix = features.pivot(index="trade_date", columns="stock_code", values="point_in_time_adjusted_close").sort_index()
        safe_matrix = features.pivot(index="trade_date", columns="stock_code", values="corporate_action_event_safe").sort_index()
        # The shared weight helper serializes symbols as strings.  Convert only
        # the compact pivot column labels, rather than duplicating strings for
        # every historical feature row.
        price_matrix.columns = price_matrix.columns.map(str)
        safe_matrix.columns = safe_matrix.columns.map(str)
        ordered_dates = [pd.Timestamp(day) for day in dates]
        values = [1.0]
        # The initial decision is made at the requested start close; its target
        # takes effect on the following trading day just like later quarters.
        try:
            initial_ranked = model.rank(features.loc[features["trade_date"].eq(ordered_dates[0])].copy())
            initial_target = _capped_score_market_cap_weights(initial_ranked.loc[initial_ranked["selected"]])
        except (ValueError, RuntimeError) as exc:
            raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "모멘텀 v2 초기 목표를 안전하게 산출할 수 없습니다.") from exc
        weights: dict[str, float] = {}
        pending_target: dict[str, float] | None = {symbol: float(weight) for symbol, weight in initial_target.items()}
        last_bucket = BacktestService._rebalance_bucket(dates[0], "QUARTERLY")
        for index, trade_date in enumerate(ordered_dates[1:], start=1):
            if pending_target is not None:
                weights = pending_target
                pending_target = None
            previous_date = ordered_dates[index - 1]
            bucket = BacktestService._rebalance_bucket(trade_date.date(), "QUARTERLY")
            if bucket != last_bucket:
                cross_section = features.loc[features["trade_date"].eq(previous_date)].copy()
                try:
                    ranked = model.rank(cross_section)
                    selected = ranked.loc[ranked["selected"]]
                    target = _capped_score_market_cap_weights(selected)
                except (ValueError, RuntimeError) as exc:
                    raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "모멘텀 v2 목표 포트폴리오를 안전하게 산출할 수 없습니다.") from exc
                # The prior quarter-end close is the decision close; apply the
                # new target before calculating the first return of this quarter.
                weights = {symbol: float(weight) for symbol, weight in target.items()}
                last_bucket = bucket
            if weights:
                symbols = list(weights)
                try:
                    current = price_matrix.loc[trade_date, symbols]
                    previous = price_matrix.loc[previous_date, symbols]
                    safe = safe_matrix.loc[trade_date, symbols]
                except KeyError as exc:
                    raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "보유 종목 가격 관측치가 없습니다.") from exc
                if current.isna().any() or previous.isna().any() or not safe.eq(True).all():
                    raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "기업행위 또는 결측 가격으로 v2 백테스트를 중단했습니다.")
                closing = {symbol: weight * float(current[symbol] / previous[symbol]) for symbol, weight in weights.items()}
                total = (1.0 - sum(weights.values())) + sum(closing.values())
                if total <= 0 or not math.isfinite(total):
                    raise NotFoundError("BACKTEST_DATA_UNAVAILABLE", "모멘텀 v2 포트폴리오 가치가 유효하지 않습니다.")
                weights = {symbol: value / total for symbol, value in closing.items() if value > 0}
                values.append(values[-1] * total)
            else:
                values.append(values[-1])
        return values

    @staticmethod
    def _build_v2_features(
        points, model: RiskAdjustedMomentumModel
    ) -> pd.DataFrame:
        """Compute v2 features with bounded per-stock working memory.

        A five-year request can contain millions of OHLCV rows.  Building the
        input frame, feature frame, risk-filter frame, and model frame for the
        complete universe at once exceeds the Production Container App memory
        limit.  Features are independent within each stock, so process one
        stock at a time and retain only the columns needed for cross-sectional
        ranking and portfolio drift.
        """
        if isinstance(points, list):
            # Test doubles and legacy repositories return lists in arbitrary
            # order; the production stream is already ordered by stock/date.
            points = iter(sorted(points, key=lambda point: (point.stock_code, point.trade_date)))
        point_groups = groupby(points, key=lambda point: point.stock_code)
        first_group = next(point_groups, None)
        if first_group is None:
            return pd.DataFrame(columns=V2_FEATURE_COLUMNS)

        pieces: list[pd.DataFrame] = []
        stock_ids: dict[str, int] = {}
        groups = chain((first_group,), point_groups)
        for stock_code, point_group in groups:
            stock_points = list(point_group)
            frame = pd.DataFrame([
                {
                    "stock_code": point.stock_code,
                    "trade_date": point.trade_date,
                    "close_price": float(point.close),
                    "listed_shares": point.listed_shares,
                    "market_cap": point.market_cap,
                    "volume": point.volume,
                    "trading_value": float(point.trading_value) if point.trading_value is not None else None,
                    "open_price": float(point.open_price) if point.open_price is not None else None,
                    "high_price": float(point.high_price) if point.high_price is not None else None,
                    "low_price": float(point.low_price) if point.low_price is not None else None,
                }
                for point in stock_points
            ])
            del stock_points
            if frame.empty:
                continue
            try:
                enriched = add_momentum_features(frame)
                filtered = apply_stock_risk_filter(enriched)
                computed = model.compute_features(filtered)
            except ValueError as exc:
                raise NotFoundError(
                    "BACKTEST_DATA_UNAVAILABLE", "모멘텀 v2 입력 데이터가 안전하지 않습니다."
                ) from exc
            piece = computed.loc[:, V2_FEATURE_COLUMNS].copy()
            # Object-backed strings are disproportionately expensive when the
            # complete multi-year cross-section is concatenated.  Stock codes
            # are only internal pivot keys here, so use stable int32 ids.
            stock_id = stock_ids.setdefault(stock_code, len(stock_ids))
            piece["stock_code"] = stock_id
            piece["stock_code"] = piece["stock_code"].astype("int32")
            piece["market_cap"] = pd.to_numeric(piece["market_cap"], errors="coerce")
            pieces.append(piece)
            del piece
            del computed, filtered, enriched, frame
            gc.collect()

        if not pieces:
            return pd.DataFrame(columns=V2_FEATURE_COLUMNS)
        return pd.concat(pieces, ignore_index=True)

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
                available_financials = [
                    point for point in financial_history.get(code, [])
                    if point.available_at <= as_of
                ]
                latest_financial = max(
                    available_financials,
                    key=lambda point: (point.period_end, point.available_at),
                    default=None,
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
