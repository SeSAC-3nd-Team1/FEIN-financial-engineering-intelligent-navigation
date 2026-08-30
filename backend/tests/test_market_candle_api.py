"""인증된 분봉 REST API 계약을 검증한다."""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes import market
from app.integrations.kis.models import MinuteCandle


class FakeMarketService:
    def get_minute_candles(self, stock_code: str, limit: int):
        assert stock_code == "005930"
        assert limit == 1
        now = datetime.now(UTC)
        return [
            MinuteCandle(
                stock_code=stock_code,
                started_at=now,
                open=Decimal("70000"),
                high=Decimal("70200"),
                low=Decimal("69900"),
                close=Decimal("70100"),
                volume=10,
                is_closed=False,
            )
        ], now, "KIS"


def test_minute_candle_endpoint_contract(monkeypatch) -> None:
    monkeypatch.setattr(market, "MarketService", FakeMarketService)
    app = FastAPI()
    app.include_router(market.router, prefix="/api/v1")
    app.dependency_overrides[current_user] = lambda: object()

    response = TestClient(app).get("/api/v1/market/stocks/005930/candles?interval=1m&limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["stock_code"] == "005930"
    assert payload["interval"] == "1m"
    assert payload["source"] == "KIS"
    assert payload["items"][0]["close"] == "70100"
    assert payload["items"][0]["is_closed"] is False


def test_minute_candle_endpoint_rejects_unsupported_interval(monkeypatch) -> None:
    monkeypatch.setattr(market, "MarketService", FakeMarketService)
    app = FastAPI()
    app.include_router(market.router, prefix="/api/v1")
    app.dependency_overrides[current_user] = lambda: object()

    response = TestClient(app).get("/api/v1/market/stocks/005930/candles?interval=5m")

    assert response.status_code == 422
