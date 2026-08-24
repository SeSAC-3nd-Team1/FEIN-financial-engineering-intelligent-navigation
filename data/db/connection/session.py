"""SQLAlchemy engine 생성과 session transaction lifecycle을 관리한다.

로컬 Compose와 Azure Database for PostgreSQL은 동일한 ``DATABASE_URL`` 계약을 사용한다.
Azure SSL 설정은 코드에 분기하지 않고 URL 옵션(예: ``?sslmode=require``)으로 전달한다.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def normalize_database_url(database_url: str) -> str:
    """일반 PostgreSQL URL을 psycopg 3 SQLAlchemy URL 형식으로 맞춘다."""

    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url.removeprefix("postgres://")
    if database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix(
            "postgresql://"
        )
    return database_url


def get_database_url() -> str:
    """credential을 코드에 넣지 않고 환경변수에서 DB 연결 URL을 읽는다."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    # HOST_DATABASE_URL은 Compose 바깥에서 script를 실행할 때만 명시적으로 사용한다.
    # 컨테이너 내부에서는 DATABASE_URL의 service hostname을 그대로 사용하는 것이 기본이다.
    database_url = os.getenv("HOST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required. Copy .env.example to .env or export it in the shell."
        )
    return normalize_database_url(database_url)


def build_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    """로컬/Azure PostgreSQL에서 공통으로 사용할 SQLAlchemy engine을 만든다.

    ``pool_pre_ping``으로 끊어진 연결을 checkout 시점에 확인하고, 장시간 살아 있는 연결이
    Azure 네트워크 정책과 충돌하지 않도록 일정 시간 후 pool connection을 재생성한다.
    """

    url = normalize_database_url(database_url) if database_url else get_database_url()
    return create_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        pool_recycle=1_800,
        connect_args={
            "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "5"))
        },
    )


@contextmanager
def session_scope(bind: Engine | Connection | None = None) -> Iterator[Session]:
    """한 작업 단위를 commit하고 예외가 발생하면 전체 transaction을 rollback한다.

    loader가 중간까지만 저장되는 상태를 만들지 않도록 session의 commit/rollback/close를
    호출자 대신 한 곳에서 보장한다.
    """

    active_bind = bind if bind is not None else build_engine()
    factory = sessionmaker(bind=active_bind, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
