"""SQLAlchemy ORM이 공통으로 사용하는 Declarative Base와 constraint naming 규칙이다."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


# Alembic migration에서 constraint 이름이 환경마다 달라지지 않도록 명시적인 규칙을 둔다.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """모든 ORM 모델이 공유하는 SQLAlchemy Declarative Base다."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
