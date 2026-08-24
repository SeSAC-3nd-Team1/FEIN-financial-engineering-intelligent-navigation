"""KIS 가격이 Redis에 저장되고 이후 cache hit로 재사용되는지 검증한다."""

from datetime import UTC, datetime
from decimal import Decimal
import json

from app.services.market import MarketService


class FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl


class FakeKis:
    def __init__(self) -> None:
        self.calls = 0

    def get_current_price(self, stock_code: str):
        self.calls += 1
        assert stock_code == "005930"
        return Decimal("70000"), datetime.now(UTC)


def test_kis_price_is_cached_in_redis_format() -> None:
    cache = FakeCache()
    kis = FakeKis()
    market = MarketService(kis=kis, cache=cache)

    first_price, first_as_of, first_source = market.get_price("005930")
    second_price, second_as_of, second_source = market.get_price("005930")

    assert first_price == second_price == Decimal("70000")
    assert first_as_of == second_as_of
    assert first_source == "KIS"
    assert second_source == "REDIS"
    assert kis.calls == 1
    assert cache.ttls["price:005930"] > 0


def test_fresh_realtime_price_has_priority_over_rest_cache() -> None:
    cache = FakeCache()
    now = datetime.now(UTC)
    cache.values["market:realtime:price:005930"] = json.dumps({
        "stock_code": "005930",
        "price": "71000",
        "change": "1000",
        "change_rate": "1.43",
        "trade_volume": 3,
        "accumulated_volume": 100,
        "traded_at": now.isoformat(),
        "received_at": now.isoformat(),
        "source": "KIS_WS",
    })
    cache.values["price:005930"] = json.dumps({"price": "70000", "as_of": now.isoformat()})
    kis = FakeKis()

    price, as_of, source = MarketService(kis=kis, cache=cache).get_price("005930")

    assert price == Decimal("71000")
    assert as_of == now
    assert source == "KIS_WS"
    assert kis.calls == 0


def test_stale_realtime_price_falls_back_to_rest_cache() -> None:
    cache = FakeCache()
    now = datetime.now(UTC)
    stale = now.replace(year=2025)
    cache.values["market:realtime:price:005930"] = json.dumps({
        "stock_code": "005930",
        "price": "71000",
        "change": "1000",
        "change_rate": "1.43",
        "trade_volume": 3,
        "accumulated_volume": 100,
        "traded_at": stale.isoformat(),
        "received_at": stale.isoformat(),
        "source": "KIS_WS",
    })
    cache.values["price:005930"] = json.dumps({"price": "70000", "as_of": now.isoformat()})
    kis = FakeKis()

    price, _, source = MarketService(kis=kis, cache=cache).get_price("005930")

    assert price == Decimal("70000")
    assert source == "REDIS"
    assert kis.calls == 0
