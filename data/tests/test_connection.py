from db.connection.session import normalize_database_url


def test_normalize_postgresql_url_uses_psycopg3() -> None:
    assert (
        normalize_database_url("postgresql://user:pass@db:5432/name")
        == "postgresql+psycopg://user:pass@db:5432/name"
    )


def test_normalize_legacy_postgres_url() -> None:
    assert (
        normalize_database_url("postgres://user:pass@db:5432/name?sslmode=require")
        == "postgresql+psycopg://user:pass@db:5432/name?sslmode=require"
    )
