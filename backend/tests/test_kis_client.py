"""KIS OAuth token을 요청 인스턴스 간에 재사용하는지 검증한다."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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
