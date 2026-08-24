"""KIS OAuth token을 요청 인스턴스 간에 재사용하는지 검증한다."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.errors import ServiceError
from app.integrations.kis.client import KisClient


class FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl


class TokenResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str | int]:
        return {"access_token": "shared-token", "expires_in": 3600}


def test_access_token_is_reused_from_shared_cache(monkeypatch) -> None:
    calls = 0

    def fake_post(*_args, **_kwargs) -> TokenResponse:
        nonlocal calls
        calls += 1
        return TokenResponse()

    monkeypatch.setattr("app.integrations.kis.client.httpx.post", fake_post)
    monkeypatch.setattr(
        "app.integrations.kis.client.settings",
        SimpleNamespace(
            kis_app_key="key",
            kis_app_secret="secret",
            kis_base_url="https://example.invalid",
            request_timeout_seconds=1,
        ),
    )
    cache = FakeCache()

    assert KisClient(cache=cache)._access_token() == "shared-token"
    assert KisClient(cache=cache)._access_token() == "shared-token"
    assert calls == 1
    assert cache.ttls[KisClient.TOKEN_CACHE_KEY] == 3540


class CandleResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "rt_cd": "0",
            "output2": [
                {
                    "stck_bsop_date": "20260824",
                    "stck_cntg_hour": "100100",
                    "stck_oprc": "70100",
                    "stck_hgpr": "70300",
                    "stck_lwpr": "70000",
                    "stck_prpr": "70200",
                    "cntg_vol": "15",
                },
                {
                    "stck_bsop_date": "20260824",
                    "stck_cntg_hour": "100000",
                    "stck_oprc": "70000",
                    "stck_hgpr": "70200",
                    "stck_lwpr": "69900",
                    "stck_prpr": "70100",
                    "cntg_vol": "10",
                },
            ],
        }


class QuoteResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "rt_cd": "0",
            "output": {
                "stck_prpr": "73400", "stck_sdpr": "72200", "prdy_vrss": "1200",
                "prdy_ctrt": "1.66", "acml_vol": "12345678",
            },
        }


def test_current_quote_maps_change_and_volume(monkeypatch) -> None:
    monkeypatch.setattr("app.integrations.kis.client.httpx.get", lambda *_args, **_kwargs: QuoteResponse())
    monkeypatch.setattr(
        "app.integrations.kis.client.settings",
        SimpleNamespace(
            kis_app_key="key", kis_app_secret="secret", kis_base_url="https://example.invalid",
            request_timeout_seconds=1,
        ),
    )
    client = KisClient()
    client._token = "existing-token"
    client._token_expires_at = 10**12

    quote = client.get_current_quote("005930")

    assert quote.price == 73400
    assert quote.previous_close == 72200
    assert quote.change_amount == 1200
    assert quote.change_rate == Decimal("1.66")
    assert quote.volume == 12345678


def test_minute_candles_reuse_client_token_and_are_sorted(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(*_args, **kwargs) -> CandleResponse:
        calls.append(kwargs)
        return CandleResponse()

    monkeypatch.setattr("app.integrations.kis.client.httpx.get", fake_get)
    monkeypatch.setattr(
        "app.integrations.kis.client.settings",
        SimpleNamespace(
            kis_app_key="key",
            kis_app_secret="secret",
            kis_base_url="https://example.invalid",
            request_timeout_seconds=1,
        ),
    )
    client = KisClient()
    client._token = "existing-token"
    client._token_expires_at = 10**12
    kst = timezone(timedelta(hours=9))

    candles, _ = client.get_minute_candles(
        "005930",
        limit=2,
        end_at=datetime(2026, 8, 24, 10, 1, 30, tzinfo=kst),
    )

    assert [candle.started_at.strftime("%H%M%S") for candle in candles] == ["100000", "100100"]
    assert [candle.close for candle in candles] == [70100, 70200]
    assert candles[0].is_closed is True
    assert candles[1].is_closed is False
    assert calls[0]["headers"]["authorization"] == "Bearer existing-token"
    assert calls[0]["headers"]["tr_id"] == "FHKST03010200"
    assert calls[0]["params"] == {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": "005930",
        "FID_INPUT_HOUR_1": "100130",
        "FID_PW_DATA_INCU_YN": "Y",
        "FID_ETC_CLS_CODE": "",
    }


def test_minute_candles_fetches_full_regular_session_with_pacing(monkeypatch) -> None:
    page_cursors: list[datetime] = []
    sleeps: list[float] = []

    def fake_page(_stock_code: str, cursor: datetime, _headers: dict[str, str]) -> list[dict[str, object]]:
        page_cursors.append(cursor)
        page_end = cursor.replace(second=0, microsecond=0)
        return [
            {
                "stck_bsop_date": started_at.strftime("%Y%m%d"),
                "stck_cntg_hour": started_at.strftime("%H%M%S"),
                "stck_oprc": "70000",
                "stck_hgpr": "70200",
                "stck_lwpr": "69900",
                "stck_prpr": "70100",
                "cntg_vol": "10",
            }
            for offset in range(30)
            for started_at in [page_end - timedelta(minutes=offset)]
        ]

    monkeypatch.setattr(
        "app.integrations.kis.client.settings",
        SimpleNamespace(
            kis_app_key="key",
            kis_app_secret="secret",
            kis_base_url="https://example.invalid",
            request_timeout_seconds=1,
            kis_rest_page_interval_seconds=0.5,
        ),
    )
    monkeypatch.setattr("app.integrations.kis.client.time.sleep", sleeps.append)
    client = KisClient()
    client._token = "existing-token"
    client._token_expires_at = 10**12
    monkeypatch.setattr(client, "_get_minute_candle_page", fake_page)
    kst = timezone(timedelta(hours=9))

    candles, _ = client.get_minute_candles(
        "005930",
        limit=390,
        end_at=datetime(2026, 8, 24, 15, 30, 30, tzinfo=kst),
    )

    assert len(candles) == 390
    assert candles[0].started_at.strftime("%H%M%S") == "090100"
    assert candles[-1].started_at.strftime("%H%M%S") == "153000"
    assert len(page_cursors) == 13
    assert sleeps == [0.5] * 12


class RateLimitResponse:
    status_code = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


def test_minute_candle_page_retries_egw00201_with_backoff(monkeypatch) -> None:
    responses = [
        RateLimitResponse({"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수 초과"}),
        CandleResponse(),
    ]
    sleeps: list[float] = []
    monkeypatch.setattr("app.integrations.kis.client.httpx.get", lambda *_args, **_kwargs: responses.pop(0))
    monkeypatch.setattr("app.integrations.kis.client.time.sleep", sleeps.append)
    monkeypatch.setattr(
        "app.integrations.kis.client.settings",
        SimpleNamespace(
            kis_app_key="key", kis_app_secret="secret", kis_base_url="https://example.invalid",
            request_timeout_seconds=1, kis_rest_page_interval_seconds=0.5,
        ),
    )
    client = KisClient()
    kst = timezone(timedelta(hours=9))

    rows = client._get_minute_candle_page(
        "005930",
        datetime(2026, 8, 24, 10, 1, tzinfo=kst),
        {"authorization": "Bearer token"},
    )

    assert len(rows) == 2
    assert sleeps == [0.5]


def test_minute_candle_page_returns_rate_limit_after_retries(monkeypatch) -> None:
    response = RateLimitResponse({"rt_cd": "1", "msg_cd": "EGW00201"})
    monkeypatch.setattr("app.integrations.kis.client.httpx.get", lambda *_args, **_kwargs: response)
    monkeypatch.setattr("app.integrations.kis.client.time.sleep", lambda _delay: None)
    monkeypatch.setattr(
        "app.integrations.kis.client.settings",
        SimpleNamespace(
            kis_app_key="key", kis_app_secret="secret", kis_base_url="https://example.invalid",
            request_timeout_seconds=1, kis_rest_page_interval_seconds=0.5,
        ),
    )
    client = KisClient()

    with pytest.raises(ServiceError) as exc_info:
        client._get_minute_candle_page(
            "005930",
            datetime(2026, 8, 24, 10, 1, tzinfo=timezone(timedelta(hours=9))),
            {"authorization": "Bearer token"},
        )

    assert exc_info.value.code == "KIS_RATE_LIMIT"
    assert exc_info.value.status_code == 503
