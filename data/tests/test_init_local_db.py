"""공용 PostgreSQL 초기화 재시도와 credential 비노출을 검증한다."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import OperationalError

from scripts import init_local_db


EFFECTIVE_AT = datetime(2026, 8, 23, tzinfo=UTC)


def database_unavailable() -> OperationalError:
    """실제 URL 없이 접속 실패와 같은 SQLAlchemy 예외를 만든다."""

    return OperationalError("connect", {}, Exception("secret-url-must-not-leak"))


def test_initialize_with_retry_recovers_from_transient_failure(monkeypatch) -> None:
    attempts = 0
    sleeps: list[float] = []

    def initialize(*_args, **_kwargs) -> int:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise database_unavailable()
        return 6

    monkeypatch.setattr(init_local_db, "initialize_database", initialize)
    monkeypatch.setattr(init_local_db.time, "sleep", sleeps.append)

    inserted = init_local_db.initialize_with_retry(
        "dev-test",
        EFFECTIVE_AT,
        max_attempts=3,
        retry_seconds=0.25,
    )

    assert inserted == 6
    assert attempts == 3
    assert sleeps == [0.25, 0.25]


def test_initialize_with_retry_hides_driver_error(monkeypatch) -> None:
    def initialize(*_args, **_kwargs) -> int:
        raise database_unavailable()

    monkeypatch.setattr(init_local_db, "initialize_database", initialize)

    with pytest.raises(RuntimeError, match="failed after 1 attempts") as error:
        init_local_db.initialize_with_retry(
            "dev-test",
            EFFECTIVE_AT,
            max_attempts=1,
            retry_seconds=0,
        )

    assert error.value.__cause__ is None
    assert "secret-url-must-not-leak" not in str(error.value)


@pytest.mark.parametrize(
    ("max_attempts", "retry_seconds", "message"),
    [(0, 1, "DB_INIT_MAX_ATTEMPTS"), (1, -1, "DB_INIT_RETRY_SECONDS")],
)
def test_initialize_with_retry_rejects_invalid_policy(
    max_attempts: int,
    retry_seconds: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        init_local_db.initialize_with_retry(
            "dev-test",
            EFFECTIVE_AT,
            max_attempts=max_attempts,
            retry_seconds=retry_seconds,
        )
