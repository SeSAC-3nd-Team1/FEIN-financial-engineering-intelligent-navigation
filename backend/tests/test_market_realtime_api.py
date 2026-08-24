"""실시간 시장가 WebSocket의 인증·구독 응답 계약을 검증한다."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import market
from app.integrations.kis.models import RealtimeQuote


def quote() -> RealtimeQuote:
    return RealtimeQuote(
        stock_code="005930",
        price=Decimal("70000"),
        change=Decimal("500"),
        change_rate=Decimal("0.72"),
        trade_volume=10,
        accumulated_volume=1_234_567,
        traded_at=datetime.fromisoformat("2026-08-24T10:31:25+09:00"),
        received_at=datetime(2026, 8, 24, 1, 31, 25, tzinfo=UTC),
    )


class FakeHub:
    configured = True
    connected = True
    last_received_at = datetime(2026, 8, 24, 1, 31, 25, tzinfo=UTC)

    def __init__(self) -> None:
        self.added: list[set[str]] = []
        self.removed = 0

    async def add_subscriber(self, stock_codes: set[str]) -> asyncio.Queue[RealtimeQuote]:
        self.added.append(stock_codes)
        queue: asyncio.Queue[RealtimeQuote] = asyncio.Queue()
        queue.put_nowait(quote())
        return queue

    async def update_subscriber(self, _queue, *, add: set[str], remove: set[str]) -> set[str]:
        return add - remove

    async def remove_subscriber(self, _queue) -> None:
        self.removed += 1


def test_authenticated_subscription_receives_normalized_price(monkeypatch) -> None:
    fake_hub = FakeHub()
    monkeypatch.setattr(market, "realtime_hub", fake_hub)
    monkeypatch.setattr(market, "_authenticate_websocket_token", lambda _token: None)
    app = FastAPI()
    app.include_router(market.router, prefix="/api/v1")

    with TestClient(app).websocket_connect("/api/v1/market/realtime") as socket:
        socket.send_json({"action": "subscribe", "token": "valid-token", "stock_codes": ["005930"]})
        assert socket.receive_json() == {
            "type": "subscribed",
            "stock_codes": ["005930"],
            "connected": True,
        }
        assert socket.receive_json() == {
            "type": "price",
            "stock_code": "005930",
            "price": "70000",
            "change": "500",
            "change_rate": "0.72",
            "trade_volume": 10,
            "accumulated_volume": 1_234_567,
            "traded_at": "2026-08-24T10:31:25+09:00",
            "received_at": "2026-08-24T01:31:25+00:00",
            "source": "KIS_WS",
            "is_stale": False,
        }

    assert fake_hub.added == [{"005930"}]
    assert fake_hub.removed == 1


def test_invalid_websocket_auth_is_rejected(monkeypatch) -> None:
    fake_hub = FakeHub()
    monkeypatch.setattr(market, "realtime_hub", fake_hub)

    def reject(_token: str) -> None:
        raise ValueError("invalid token")

    monkeypatch.setattr(market, "_authenticate_websocket_token", reject)
    app = FastAPI()
    app.include_router(market.router, prefix="/api/v1")

    with TestClient(app).websocket_connect("/api/v1/market/realtime") as socket:
        socket.send_json({"action": "subscribe", "token": "invalid-token", "stock_codes": ["005930"]})
        assert socket.receive_json() == {
            "type": "error",
            "code": "INVALID_SUBSCRIPTION",
            "message": "인증 토큰과 유효한 구독 종목이 필요합니다.",
        }

    assert fake_hub.added == []
