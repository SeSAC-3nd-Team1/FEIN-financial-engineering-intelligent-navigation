"""SQLAlchemy engine and session lifecycle.

The same ``DATABASE_URL`` contract is used for local Compose and Azure Database for
PostgreSQL. Azure-specific SSL options should be supplied in the URL, for example
``?sslmode=require``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def normalize_database_url(database_url: str) -> str:
    """Select psycopg 3 while accepting common PostgreSQL URL formats."""

    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url.removeprefix("postgres://")
    if database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix(
            "postgresql://"
        )
    return database_url


def get_database_url() -> str:
    """Return the configured database URL without embedding credentials in code."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    # HOST_DATABASE_URL is an explicit opt-in for scripts run outside Compose.
    database_url = os.getenv("HOST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required. Copy .env.example to .env or export it in the shell."
        )
    return normalize_database_url(database_url)


def build_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    """Build a production-safe SQLAlchemy engine for local or Azure PostgreSQL."""

    url = normalize_database_url(database_url) if database_url else get_database_url()
    return create_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        pool_recycle=1_800,
    )


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Commit a unit of work, rolling it back if an exception is raised."""

    active_engine = engine or build_engine()
    factory = sessionmaker(bind=active_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
