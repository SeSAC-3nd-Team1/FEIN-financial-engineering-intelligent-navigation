from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from scripts.seed_signup_terms import TERM_TITLES, build_seed_statement, build_term_rows


def test_build_term_rows_uses_existing_required_catalog() -> None:
    effective_at = datetime(2026, 8, 23, tzinfo=UTC)
    rows = build_term_rows("dev-test", effective_at, "https://terms.example")

    assert {row["term_code"] for row in rows} == set(TERM_TITLES)
    assert len(rows) == 6
    assert all(row["version"] == "dev-test" for row in rows)
    assert all(row["is_required"] is True for row in rows)
    assert all(row["effective_at"] == effective_at for row in rows)
    assert all(row["content_reference"].endswith(f"/{row['term_code']}/dev-test") for row in rows)


def test_seed_statement_ignores_duplicate_code_version() -> None:
    rows = build_term_rows("dev-test", datetime(2026, 8, 23, tzinfo=UTC))
    sql = str(build_seed_statement(rows).compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT (term_code, version) DO NOTHING" in sql
