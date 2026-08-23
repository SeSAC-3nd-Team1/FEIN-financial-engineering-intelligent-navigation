"""KIS OAuth token을 요청 인스턴스 간에 재사용하는지 검증한다."""

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
