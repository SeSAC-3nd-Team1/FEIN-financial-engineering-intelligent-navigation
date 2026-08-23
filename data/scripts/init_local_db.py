"""로컬 Docker DB에 migration과 명시적인 개발용 약관 seed를 적용한다."""

import os

from alembic import command
from alembic.config import Config

from scripts.seed_signup_terms import parse_timestamp, seed_signup_terms


def main() -> None:
    version = os.getenv("SIGNUP_TERMS_VERSION", "dev-20260823")
    effective_at = parse_timestamp(
        os.getenv("SIGNUP_TERMS_EFFECTIVE_AT", "2026-08-23T00:00:00+09:00")
    )
    content_base_url = os.getenv("SIGNUP_TERMS_CONTENT_BASE_URL") or None

    command.upgrade(Config("alembic.ini"), "head")
    inserted_count = seed_signup_terms(version, effective_at, content_base_url)
    print(f"local database ready: {inserted_count} terms inserted, version={version}")


if __name__ == "__main__":
    main()
