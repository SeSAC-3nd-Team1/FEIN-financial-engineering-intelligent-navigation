"""Redis 우선 현재가 조회와 KIS fallback."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
import json
import logging

import redis

from app.core.config import settings
from app.integrations.kis.client import KisClient
from app.integrations.kis.hub import REALTIME_PRICE_KEY_PREFIX
from app.core.errors import NotFoundError
from app.integrations.kis.models import CurrentQuote, MinuteCandle, RealtimeQuote
from app.repositories.market_data import MarketDataRepository
from app.schemas.api import (
    StockChartItemResponse,
    StockChartResponse,
    StockSummaryResponse,
)

logger = logging.getLogger(__name__)


class MarketService:
    def __init__(
        self, kis: KisClient | None = None, cache: redis.Redis | None = None
    ) -> None:
        self.cache = cache or redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=1
        )
        self.kis = kis or KisClient(cache=self.cache)

    def get_quote(self, stock_code: str) -> CurrentQuote:
        realtime_key = f"{REALTIME_PRICE_KEY_PREFIX}{stock_code}"
        try:
            realtime_cached = self.cache.get(realtime_key)
            if realtime_cached:
                quote = RealtimeQuote.from_cache_json(realtime_cached)
                age = (
                    datetime.now(UTC) - quote.received_at.astimezone(UTC)
                ).total_seconds()
                if age <= settings.realtime_price_stale_seconds:
                    return CurrentQuote(
                        stock_code=stock_code,
                        price=quote.price,
                        previous_close=(
                            quote.price - quote.change
                            if quote.price - quote.change > 0
                            else None
                        ),
                        change_amount=quote.change,
                        change_rate=quote.change_rate,
                        volume=quote.accumulated_volume,
                        as_of=quote.traded_at,
                        source="KIS_WS",
                    )
                logger.info(
                    "Ignoring stale realtime price stock_code=%s age_seconds=%.3f",
                    stock_code,
                    age,
                )
        except (redis.RedisError, ValueError, TypeError):
            logger.warning("Redis realtime price unavailable stock_code=%s", stock_code)

        key = f"price:{stock_code}"
        try:
            cached = self.cache.get(key)
            if cached:
                payload = json.loads(cached)
                return CurrentQuote(
                    stock_code=stock_code,
                    price=Decimal(payload["price"]),
                    previous_close=(
                        Decimal(payload["previous_close"])
                        if payload.get("previous_close") is not None
                        else None
                    ),
                    change_amount=(
                        Decimal(payload["change_amount"])
                        if payload.get("change_amount") is not None
                        else None
                    ),
                    change_rate=(
                        Decimal(payload["change_rate"])
                        if payload.get("change_rate") is not None
                        else None
                    ),
                    volume=(
                        int(payload["volume"])
                        if payload.get("volume") is not None
                        else None
                    ),
                    as_of=datetime.fromisoformat(payload["as_of"]),
                    source="REDIS",
                )
        except (redis.RedisError, ValueError, KeyError, TypeError):
            logger.warning("Redis price cache unavailable stock_code=%s", stock_code)

        if hasattr(self.kis, "get_current_quote"):
            quote = self.kis.get_current_quote(stock_code)
        else:
            price, as_of = self.kis.get_current_price(stock_code)
            quote = CurrentQuote(stock_code, price, None, None, None, None, as_of)
        try:
            self.cache.setex(
                key,
                settings.price_cache_ttl_seconds,
                json.dumps(
                    {
                        "price": str(quote.price),
                        "previous_close": (
                            str(quote.previous_close)
                            if quote.previous_close is not None
                            else None
                        ),
                        "change_amount": (
                            str(quote.change_amount)
                            if quote.change_amount is not None
                            else None
                        ),
                        "change_rate": (
                            str(quote.change_rate)
                            if quote.change_rate is not None
                            else None
                        ),
                        "volume": quote.volume,
                        "as_of": quote.as_of.isoformat(),
                    }
                ),
            )
        except redis.RedisError:
            logger.warning("Redis price cache write failed stock_code=%s", stock_code)
        return quote

    def get_price(self, stock_code: str) -> tuple[Decimal, datetime, str]:
        quote = self.get_quote(stock_code)
        return quote.price, quote.as_of, quote.source.removesuffix("_REST")

    def get_minute_candles(
        self,
        stock_code: str,
        limit: int,
    ) -> tuple[list[MinuteCandle], datetime, str]:
        key = f"market:candles:1m:{stock_code}"
        try:
            cached = self.cache.get(key)
            if cached:
                payload = json.loads(cached)
                if int(payload["requested_limit"]) >= limit:
                    candles = [
                        MinuteCandle.from_payload(stock_code, item)
                        for item in payload["items"]
                    ]
                    return (
                        candles[-limit:],
                        datetime.fromisoformat(payload["as_of"]),
                        "REDIS",
                    )
        except (redis.RedisError, ValueError, KeyError, TypeError):
            logger.warning(
                "Redis minute candle cache unavailable stock_code=%s", stock_code
            )

        candles, as_of = self.kis.get_minute_candles(stock_code, limit=limit)
        cache_payload = {
            "requested_limit": limit,
            "as_of": as_of.isoformat(),
            "items": [candle.to_payload() for candle in candles],
        }
        try:
            self.cache.setex(
                key,
                settings.minute_candle_cache_ttl_seconds,
                json.dumps(cache_payload, ensure_ascii=False, separators=(",", ":")),
            )
        except redis.RedisError:
            logger.warning(
                "Redis minute candle cache write failed stock_code=%s", stock_code
            )
        return candles, as_of, "KIS"


PERIOD_DAYS = {"1W": 7, "3M": 93, "6M": 186, "1Y": 366, "5Y": 1830}


def _positive_ratio(
    numerator: Decimal | None,
    denominator: Decimal | None,
    multiplier: Decimal = Decimal("1"),
) -> Decimal | None:
    """분모가 양수인 실제 값만 계산하고 손실/자본잠식 기업은 null로 둔다."""

    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator * multiplier


def _dividend_yield(
    dividend_per_share: Decimal | None,
    price: Decimal | None,
    reported_yield: Decimal | None,
) -> Decimal | None:
    """공시 수익률을 우선하고 없을 때만 DPS와 저장된 가격으로 계산한다."""

    if reported_yield is not None:
        return reported_yield
    return _positive_ratio(dividend_per_share, price, Decimal("100"))


class StockMarketService:
    """KIS·KRX·OpenDART를 Frontend용 단일 계약으로 조합한다."""

    def __init__(
        self, repository: MarketDataRepository, live_market: MarketService | None = None
    ) -> None:
        self.repository = repository
        self.live_market = live_market or MarketService()

    def summary(self, stock_code: str) -> StockSummaryResponse:
        stock = self.repository.stock(stock_code)
        if stock is None:
            raise NotFoundError("STOCK_NOT_FOUND", "KRX 종목정보를 찾을 수 없습니다.")
        daily = self.repository.latest_price(stock_code)
        company = self.repository.company(stock_code)
        financial = self.repository.latest_annual_financial(stock_code)
        try:
            dividend = self.repository.latest_dividend(stock_code)
        except Exception as exc:
            # 배당 보조 데이터의 schema/DB 장애가 종목 상세 전체를 실패시키지 않게 격리한다.
            logger.warning(
                "Dividend lookup unavailable stock_code=%s error=%s",
                stock_code,
                type(exc).__name__,
            )
            dividend = None

        dividend_price = None
        dividend_price_source = None
        if (
            dividend is not None
            and dividend.reported_dividend_yield is None
            and dividend.dividend_per_share is not None
            and daily is not None
            and daily.close_price > 0
        ):
            dividend_price = daily.close_price
            dividend_price_source = daily.source
        dividend_yield = _dividend_yield(
            dividend.dividend_per_share if dividend else None,
            dividend_price,
            dividend.reported_dividend_yield if dividend else None,
        )

        market_cap = daily.market_cap if daily else None
        net_income = financial.net_income if financial else None
        total_equity = financial.total_equity if financial else None
        description_parts: list[str] = []
        if company:
            description_parts.append(
                f"{company.corp_name}은(는) {stock.market} 상장 기업입니다."
            )
            if company.established_date:
                description_parts.append(
                    f"설립일은 {company.established_date.isoformat()}입니다."
                )
            if company.industry_code:
                description_parts.append(
                    f"OpenDART 업종 코드는 {company.industry_code}입니다."
                )

        return StockSummaryResponse(
            stock_code=stock.stock_code,
            stock_name=stock.stock_name,
            market=stock.market,
            sector=stock.sector or (company.industry_code if company else None),
            listing_date=stock.listing_date,
            listed_shares=stock.listed_shares,
            security_type=stock.security_type,
            description=" ".join(description_parts) or None,
            price=None,
            previous_close=None,
            change_amount=None,
            change_rate=None,
            volume=None,
            market_cap=market_cap,
            per=_positive_ratio(market_cap, net_income),
            pbr=_positive_ratio(market_cap, total_equity),
            roe=_positive_ratio(net_income, total_equity, Decimal("100")),
            dividend_yield=dividend_yield,
            financial_year=financial.business_year if financial else None,
            as_of=(
                datetime.combine(daily.as_of, time.min, tzinfo=UTC) if daily else None
            ),
            sources={
                "price": None,
                "market": daily.source if daily else stock.source,
                "financial": "OpenDART" if financial else None,
                "dividend": dividend.source if dividend else None,
                "dividend_price": dividend_price_source,
            },
        )

    def chart(self, stock_code: str, period: str) -> StockChartResponse:
        if period == "1D":
            # 정규장 6시간 30분 전체를 조회해 API period와 UI의 '1일' 의미를 일치시킨다.
            candles, as_of, source = self.live_market.get_minute_candles(
                stock_code, 390
            )
            return StockChartResponse(
                stock_code=stock_code,
                period=period,
                source=source,
                as_of=as_of,
                items=[
                    StockChartItemResponse(
                        date=item.started_at.isoformat(),
                        open=item.open,
                        high=item.high,
                        low=item.low,
                        close=item.close,
                        volume=item.volume,
                    )
                    for item in candles
                ],
            )
        if self.repository.stock(stock_code) is None:
            raise NotFoundError("STOCK_NOT_FOUND", "KRX 종목정보를 찾을 수 없습니다.")
        latest = self.repository.latest_price(stock_code)
        if latest is None:
            raise NotFoundError(
                "CHART_DATA_UNAVAILABLE", "해당 종목의 KRX 일별시세가 없습니다."
            )
        # 시스템 시각보다 KRX 적재일이 늦을 수 있으므로 최신 실제 거래일을 기간의 끝으로 삼는다.
        start_date = latest.trade_date - timedelta(days=PERIOD_DAYS[period])
        prices = self.repository.prices_since(stock_code, start_date)
        if not prices:
            raise NotFoundError(
                "CHART_DATA_UNAVAILABLE", "해당 기간의 KRX 일별시세가 없습니다."
            )
        return StockChartResponse(
            stock_code=stock_code,
            period=period,
            source="KRX",
            as_of=datetime.combine(prices[-1].as_of, time.min, tzinfo=UTC),
            items=[
                StockChartItemResponse(
                    date=item.trade_date.isoformat(),
                    open=item.open_price,
                    high=item.high_price,
                    low=item.low_price,
                    close=item.close_price,
                    volume=item.volume,
                )
                for item in prices
            ],
        )
