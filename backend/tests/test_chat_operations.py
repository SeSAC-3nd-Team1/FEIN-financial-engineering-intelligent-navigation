from app.core.chat_observability import check_rate_limit, metric_snapshot


class FakeRedis:
    def __init__(self, count: int) -> None:
        self.count = count
        self.expired = None

    def incr(self, key: str) -> int:
        return self.count

    def expire(self, key: str, seconds: int) -> bool:
        self.expired = (key, seconds)
        return True


def test_rate_limit_allows_request_at_limit() -> None:
    redis = FakeRedis(1)

    assert check_rate_limit(redis, key="ip:127.0.0.1", limit=3, window_seconds=60)


def test_rate_limit_rejects_request_over_limit() -> None:
    assert not check_rate_limit(FakeRedis(4), key="user:7", limit=3, window_seconds=60)


def test_metric_snapshot_is_safe_copy() -> None:
    snapshot = metric_snapshot()
    snapshot["unexpected"] = 1
    assert metric_snapshot().get("unexpected") is None
