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


def test_normalize_azure_url_preserves_ssl_requirement() -> None:
    azure_url = (
        "postgresql://app_user:encoded%40password@team-dev.postgres.database.azure.com:5432/"
        "app?sslmode=require"
    )

    normalized = normalize_database_url(azure_url)

    assert normalized.startswith("postgresql+psycopg://")
    assert normalized.endswith("?sslmode=require")
    assert "encoded%40password" in normalized
