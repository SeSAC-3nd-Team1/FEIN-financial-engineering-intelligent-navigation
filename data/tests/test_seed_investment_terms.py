"""가상투자 약관 seed의 버전 보존과 멱등 SQL을 검증한다."""

from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from scripts.seed_investment_terms import (
    INVESTMENT_TERM_TITLES,
    build_investment_seed_statement,
    build_investment_term_rows,
)


def test_build_investment_term_rows_marks_all_terms_required() -> None:
    effective_at = datetime(2026, 8, 24, tzinfo=UTC)
    rows = build_investment_term_rows("dev-test", effective_at, "https://terms.example")

    assert {row["term_code"] for row in rows} == set(INVESTMENT_TERM_TITLES)
    assert all(row["is_required"] is True for row in rows)
    assert all(row["effective_at"] == effective_at for row in rows)
    assert all(row["content_reference"].endswith(f"/{row['term_code']}/dev-test") for row in rows)


def test_investment_seed_statement_ignores_duplicate_code_version() -> None:
    rows = build_investment_term_rows("dev-test", datetime(2026, 8, 24, tzinfo=UTC))
    sql = str(build_investment_seed_statement(rows).compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT (term_code, version) DO NOTHING" in sql
