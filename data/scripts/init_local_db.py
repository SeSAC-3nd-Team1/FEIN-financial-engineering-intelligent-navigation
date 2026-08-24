"""로컬 또는 Azure 개발 DB에 migration과 약관 seed를 안전하게 적용한다."""

import os
import time
from datetime import datetime

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from db.connection import build_engine
from scripts.seed_investment_terms import seed_investment_terms
from scripts.seed_signup_terms import parse_timestamp, seed_signup_terms


# 모든 개발자의 db-init이 같은 키를 사용해야 migration과 seed가 한 번에 하나씩 실행된다.
DB_INIT_ADVISORY_LOCK_ID = 2_026_082_300_012


def initialize_database(
    version: str,
    effective_at: datetime,
    content_base_url: str | None = None,
    *,
    investment_version: str | None = None,
    investment_effective_at: datetime | None = None,
    investment_content_base_url: str | None = None,
) -> int:
    """하나의 transaction advisory lock 안에서 migration과 seed를 수행한다.

    session/transaction 범위 lock은 성공 시 commit, 실패 시 rollback과 함께 자동 해제된다.
    따라서 공용 Azure DB에서 여러 컨테이너가 동시에 시작해도 DDL이 겹치지 않고,
    기존 사용자나 거래 데이터는 변경하지 않는다.
    """

    engine = build_engine()
    with engine.begin() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": DB_INIT_ADVISORY_LOCK_ID},
        )
        alembic_config = Config("alembic.ini")
        alembic_config.attributes["connection"] = connection
        command.upgrade(alembic_config, "head")
        signup_count = seed_signup_terms(version, effective_at, content_base_url, bind=connection)
        investment_count = seed_investment_terms(
            investment_version or version,
            investment_effective_at or effective_at,
            investment_content_base_url,
            bind=connection,
        )
        return signup_count + investment_count


def initialize_with_retry(
    version: str,
    effective_at: datetime,
    content_base_url: str | None = None,
    *,
    investment_version: str | None = None,
    investment_effective_at: datetime | None = None,
    investment_content_base_url: str | None = None,
    max_attempts: int,
    retry_seconds: float,
) -> int:
    """Compose 시작 직후와 일시적 Azure 접속 실패만 제한적으로 재시도한다."""

    if max_attempts < 1:
        raise ValueError("DB_INIT_MAX_ATTEMPTS must be at least 1")
    if retry_seconds < 0:
        raise ValueError("DB_INIT_RETRY_SECONDS must be non-negative")

    for attempt in range(1, max_attempts + 1):
        try:
            return initialize_database(
                version,
                effective_at,
                content_base_url,
                investment_version=investment_version,
                investment_effective_at=investment_effective_at,
                investment_content_base_url=investment_content_base_url,
            )
        except OperationalError:
            # driver 예외에는 connection string이 포함될 수 있어 credential을 로그에 쓰지 않는다.
            if attempt == max_attempts:
                raise RuntimeError(
                    f"database initialization failed after {max_attempts} attempts"
                ) from None
            print(f"database unavailable; retrying ({attempt}/{max_attempts})")
            time.sleep(retry_seconds)
    raise AssertionError("unreachable")


def main() -> None:
    version = os.getenv("SIGNUP_TERMS_VERSION", "dev-20260823")
    effective_at = parse_timestamp(
        os.getenv("SIGNUP_TERMS_EFFECTIVE_AT", "2026-08-23T00:00:00+09:00")
    )
    content_base_url = os.getenv("SIGNUP_TERMS_CONTENT_BASE_URL") or None
    investment_version = os.getenv("INVESTMENT_TERMS_VERSION", "dev-20260824")
    investment_effective_at = parse_timestamp(
        os.getenv("INVESTMENT_TERMS_EFFECTIVE_AT", "2026-08-24T00:00:00+09:00")
    )
    investment_content_base_url = os.getenv("INVESTMENT_TERMS_CONTENT_BASE_URL") or None
    max_attempts = int(os.getenv("DB_INIT_MAX_ATTEMPTS", "30"))
    retry_seconds = float(os.getenv("DB_INIT_RETRY_SECONDS", "2"))

    inserted_count = initialize_with_retry(
        version,
        effective_at,
        content_base_url,
        investment_version=investment_version,
        investment_effective_at=investment_effective_at,
        investment_content_base_url=investment_content_base_url,
        max_attempts=max_attempts,
        retry_seconds=retry_seconds,
    )
    print(
        "database ready: "
        f"{inserted_count} terms inserted, signup_version={version}, "
        f"investment_version={investment_version}"
    )


if __name__ == "__main__":
    main()
