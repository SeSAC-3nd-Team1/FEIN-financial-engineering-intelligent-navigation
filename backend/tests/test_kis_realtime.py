"""KIS 실시간 체결가 protocol과 Redis fan-out을 검증한다."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import json
import time

import pytest

from app.integrations.kis.hub import KisRealtimeHub, REALTIME_PRICE_KEY_PREFIX
from app.integrations.kis.models import RealtimeQuote
from app.integrations.kis.parser import KIS_REALTIME_PRICE_FIELD_COUNT, parse_realtime_price_frame
from app.integrations.kis.realtime import KisRealtimeClient


def realtime_row(
    stock_code: str = "005930",
    *,
    price: str = "70000",
    sign: str = "2",
    change: str = "500",
    change_rate: str = "0.72",
) -> list[str]:
    row = ["0"] * KIS_REALTIME_PRICE_FIELD_COUNT
    row[0] = stock_code
    row[1] = "103125"
    row[2] = price
    row[3] = sign
    row[4] = change
    row[5] = change_rate
    row[12] = "10"
    row[13] = "1234567"
    row[33] = "20260824"
    return row


def frame(*rows: list[str]) -> str:
    return f"0|H0STCNT0|{len(rows)}|" + "^".join(value for row in rows for value in row)


def quote() -> RealtimeQuote:
    return RealtimeQuote(
        stock_code="005930",
        price=Decimal("70000"),
        change=Decimal("500"),
        change_rate=Decimal("0.72"),
        trade_volume=10,
        accumulated_volume=1_234_567,
        traded_at=datetime.fromisoformat("2026-08-24T10:31:25+09:00"),
        received_at=datetime(2026, 8, 24, 1, 31, 25, 100000, tzinfo=UTC),
    )


def test_parse_realtime_price_frame() -> None:
    result = parse_realtime_price_frame(
        frame(realtime_row()),
        received_at=datetime(2026, 8, 24, 1, 31, 25, 100000, tzinfo=UTC),
    )

    assert result == [quote()]


def test_parse_multiple_rows_and_negative_change() -> None:
    result = parse_realtime_price_frame(
        frame(
            realtime_row(),
            realtime_row("000660", price="250000", sign="5", change="1000", change_rate="0.40"),
        ),
        received_at=datetime(2026, 8, 24, 1, 31, 25, 100000, tzinfo=UTC),
    )

    assert [item.stock_code for item in result] == ["005930", "000660"]
    assert result[1].change == Decimal("-1000")
    assert result[1].change_rate == Decimal("-0.40")


@pytest.mark.parametrize(
    "raw",
    [
        "0|H0STCNT0|1|too^short",
        frame(realtime_row(price="0")),
        frame(realtime_row(price="NaN")),
        frame(realtime_row(stock_code="bad")),
    ],
)
def test_invalid_realtime_frame_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_realtime_price_frame(raw)


def test_subscription_message_never_contains_account_or_order_data() -> None:
    client = KisRealtimeClient()
    client._approval_key = "approval-test"  # protocol unit test: external authentication is not called
    client._approval_expires_at = time.monotonic() + 60

    message = json.loads(asyncio.run(client.subscription_message("005930", subscribe=True)))

    assert message["body"]["input"] == {"tr_id": "H0STCNT0", "tr_key": "005930"}
    assert message["header"]["tr_type"] == "1"
    serialized = json.dumps(message).lower()
    assert "account" not in serialized
    assert "order" not in serialized

    unsubscribe = json.loads(asyncio.run(client.subscription_message("005930", subscribe=False)))
    assert unsubscribe["header"]["tr_type"] == "2"


def test_pingpong_system_message_is_detected() -> None:
    payload = KisRealtimeClient.system_message('{"header":{"tr_id":"PINGPONG"}}')
    assert payload is not None
    assert KisRealtimeClient.is_pingpong(payload)
    assert KisRealtimeClient.system_message("not-json") is None


class FakeAsyncCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl


class FakeRealtimeClient:
    configured = True

    async def aclose(self) -> None:
        return None


def test_hub_caches_and_fans_out_latest_quote() -> None:
    async def scenario() -> None:
        cache = FakeAsyncCache()
        hub = KisRealtimeHub(client=FakeRealtimeClient(), cache=cache)
        subscriber: asyncio.Queue[RealtimeQuote] = asyncio.Queue(maxsize=1)
        hub._subscribers["005930"].add(subscriber)

        await hub._publish(quote())

        assert await subscriber.get() == quote()
        key = f"{REALTIME_PRICE_KEY_PREFIX}005930"
        assert RealtimeQuote.from_cache_json(cache.values[key]) == quote()
        assert cache.ttls[key] > 0

    asyncio.run(scenario())


def test_hub_deduplicates_upstream_subscription_for_multiple_clients() -> None:
    async def scenario() -> None:
        hub = KisRealtimeHub(client=FakeRealtimeClient(), cache=FakeAsyncCache())
        # 이 test task를 runner 자리로 사용해 실제 network task 생성을 막는다.
        hub._runner = asyncio.current_task()

        first = await hub.add_subscriber({"005930"})
        second = await hub.add_subscriber({"005930"})

        assert len(hub._subscribers["005930"]) == 2
        assert await hub._commands.get() == (True, "005930")
        assert hub._commands.empty()

        await hub.remove_subscriber(first)
        assert len(hub._subscribers["005930"]) == 1
        assert hub._commands.empty()

        await hub.remove_subscriber(second)
        assert "005930" not in hub._subscribers
        assert await hub._commands.get() == (False, "005930")

    asyncio.run(scenario())
