"""실시간 시장가 WebSocket의 인증·구독 응답 계약을 검증한다."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from starlette.websockets import WebSocketDisconnect

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


def create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(market.router, prefix="/api/v1")
    return app


def assert_websocket_closed(socket, expected_code: int) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        socket.receive_json()
    assert exc_info.value.code == expected_code


def access_token() -> str:
    return market.jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        market.settings.jwt_secret,
        algorithm=market.settings.jwt_algorithm,
    )


class FakeSession:
    def __init__(self, *, user=None, error: Exception | None = None) -> None:
        self.user = user
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def get(self, *_args):
        if self.error:
            raise self.error
        return self.user


def test_authenticated_subscription_receives_normalized_price(monkeypatch) -> None:
    fake_hub = FakeHub()
    monkeypatch.setattr(market, "realtime_hub", fake_hub)
    monkeypatch.setattr(market, "_authenticate_websocket_token", lambda _token: None)
    app = create_app()

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
        raise market.WebSocketTokenError("invalid token")

    monkeypatch.setattr(market, "_authenticate_websocket_token", reject)
    app = create_app()

    with TestClient(app).websocket_connect("/api/v1/market/realtime") as socket:
        socket.send_json({"action": "subscribe", "token": "invalid-token", "stock_codes": ["005930"]})
        assert socket.receive_json() == {
            "type": "error",
            "code": "INVALID_TOKEN",
            "message": "유효한 인증 토큰이 필요합니다.",
        }
        assert_websocket_closed(socket, 4401)

    assert fake_hub.added == []


def test_missing_websocket_token_is_rejected_as_invalid_token(monkeypatch) -> None:
    fake_hub = FakeHub()
    monkeypatch.setattr(market, "realtime_hub", fake_hub)
    app = create_app()

    with TestClient(app).websocket_connect("/api/v1/market/realtime") as socket:
        socket.send_json({"action": "subscribe", "stock_codes": ["005930"]})
        assert socket.receive_json() == {
            "type": "error",
            "code": "INVALID_TOKEN",
            "message": "유효한 인증 토큰이 필요합니다.",
        }
        assert_websocket_closed(socket, 4401)

    assert fake_hub.added == []


def test_malformed_initial_subscription_is_rejected_separately(monkeypatch) -> None:
    fake_hub = FakeHub()
    monkeypatch.setattr(market, "realtime_hub", fake_hub)
    app = create_app()

    with TestClient(app).websocket_connect("/api/v1/market/realtime") as socket:
        socket.send_json({"action": "subscribe", "token": "valid-token", "stock_codes": ["invalid"]})
        assert socket.receive_json() == {
            "type": "error",
            "code": "INVALID_SUBSCRIPTION",
            "message": "구독 요청 형식이 올바르지 않습니다.",
        }
        assert_websocket_closed(socket, 4400)

    assert fake_hub.added == []


def test_invalid_initial_subscription_is_rejected_separately(monkeypatch) -> None:
    fake_hub = FakeHub()
    monkeypatch.setattr(market, "realtime_hub", fake_hub)
    app = create_app()

    with TestClient(app).websocket_connect("/api/v1/market/realtime") as socket:
        socket.send_json({"action": "unsubscribe", "token": "valid-token", "stock_codes": ["005930"]})
        assert socket.receive_json() == {
            "type": "error",
            "code": "INVALID_SUBSCRIPTION",
            "message": "최초 요청은 종목 구독이어야 합니다.",
        }
        assert_websocket_closed(socket, 4400)

    assert fake_hub.added == []


def test_initial_subscription_timeout_is_reported_separately(monkeypatch) -> None:
    fake_hub = FakeHub()
    monkeypatch.setattr(market, "realtime_hub", fake_hub)

    async def timeout(*_args, **_kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(market, "_receive_subscription", timeout)
    app = create_app()

    with TestClient(app).websocket_connect("/api/v1/market/realtime") as socket:
        assert socket.receive_json() == {
            "type": "error",
            "code": "SUBSCRIPTION_TIMEOUT",
            "message": "초기 구독 요청 시간이 초과되었습니다.",
        }
        assert_websocket_closed(socket, 4408)

    assert fake_hub.added == []


def test_websocket_auth_dependency_failure_is_internal_error(monkeypatch) -> None:
    fake_hub = FakeHub()
    monkeypatch.setattr(market, "realtime_hub", fake_hub)

    def unavailable(_token: str) -> None:
        raise market.WebSocketAuthUnavailable("database unavailable")

    monkeypatch.setattr(market, "_authenticate_websocket_token", unavailable)
    app = create_app()

    with TestClient(app).websocket_connect("/api/v1/market/realtime") as socket:
        socket.send_json({"action": "subscribe", "token": "valid-token", "stock_codes": ["005930"]})
        assert socket.receive_json() == {
            "type": "error",
            "code": "AUTH_SERVICE_UNAVAILABLE",
            "message": "인증 서비스를 사용할 수 없습니다.",
        }
        assert_websocket_closed(socket, 1011)

    assert fake_hub.added == []


def test_token_authenticator_rejects_invalid_jwt() -> None:
    with pytest.raises(market.WebSocketTokenError):
        market._authenticate_websocket_token("not-a-jwt")


def test_token_authenticator_rejects_inactive_user(monkeypatch) -> None:
    monkeypatch.setattr(market, "SessionLocal", lambda: FakeSession(user=None))

    with pytest.raises(market.WebSocketTokenError):
        market._authenticate_websocket_token(access_token())


def test_token_authenticator_maps_database_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        market,
        "SessionLocal",
        lambda: FakeSession(error=SQLAlchemyError("database unavailable")),
    )

    with pytest.raises(market.WebSocketAuthUnavailable):
        market._authenticate_websocket_token(access_token())
