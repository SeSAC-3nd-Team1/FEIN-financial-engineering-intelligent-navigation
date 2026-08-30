"""DB engine과 요청 단위 transaction session."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


engine = create_engine(
    normalize_url(settings.database_url),
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
