"""행 목록과 pandas DataFrame을 PostgreSQL에 chunk 단위로 UPSERT하는 공통 유틸이다."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import pandas as pd
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


IMMUTABLE_COLUMNS = {"created_at"}


def _chunks(rows: Sequence[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    """대량 INSERT가 지나치게 큰 statement가 되지 않도록 row를 고정 크기로 나눈다."""

    for start in range(0, len(rows), size):
        yield list(rows[start : start + size])


def _python_value(value: Any) -> Any:
    """pandas/numpy scalar를 psycopg가 처리할 수 있는 Python 기본 타입으로 변환한다."""

    if isinstance(value, pd.Timestamp):
        return value.date() if value == value.normalize() else value.to_pydatetime()
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def dataframe_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame row를 DBAPI 호환 Python 값으로 구성된 dict 목록으로 변환한다."""

    return [
        {column: _python_value(value) for column, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def upsert_rows(
    session: Session,
    model: type,
    rows: Sequence[dict[str, Any]],
    *,
    conflict_columns: Sequence[str],
    update_columns: Sequence[str] | None = None,
    chunk_size: int = 1_000,
) -> int:
    """PostgreSQL ``ON CONFLICT DO UPDATE``로 row를 멱등하게 적재한다.

    ``conflict_columns``는 실제 PK 또는 UNIQUE 제약과 일치해야 한다. 별도 지정이 없으면
    충돌키, PK, ``created_at``을 제외한 입력 컬럼을 갱신한다.
    """

    if not rows:
        return 0
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")

    table = model.__table__
    valid_columns = {column.name for column in table.columns}
    unknown = set().union(*(row.keys() for row in rows)) - valid_columns
    if unknown:
        raise ValueError(f"Unknown columns for {table.fullname}: {sorted(unknown)}")
    if missing := set(conflict_columns) - valid_columns:
        raise ValueError(f"Unknown conflict columns: {sorted(missing)}")

    # PostgreSQL은 하나의 INSERT statement 안에서 같은 conflict key를 두 번 update할 수 없다.
    # 공공 API 한 page에 완전히 같은 key가 중복될 수 있으므로 마지막 row를 남겨 먼저 정리한다.
    deduplicated: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row.get(column) for column in conflict_columns)
        deduplicated[key] = row
    prepared_rows = list(deduplicated.values())

    supplied_columns = set().union(*(row.keys() for row in rows))
    primary_keys = {column.name for column in table.primary_key.columns}
    protected = primary_keys | set(conflict_columns) | IMMUTABLE_COLUMNS
    columns_to_update = (
        list(update_columns)
        if update_columns is not None
        else sorted(supplied_columns - protected - {"updated_at"})
    )
    if invalid_updates := set(columns_to_update) - valid_columns:
        raise ValueError(f"Unknown update columns: {sorted(invalid_updates)}")

    affected = 0
    for batch in _chunks(prepared_rows, chunk_size):
        statement = insert(table).values(batch)
        update_values = {
            column_name: statement.excluded[column_name]
            for column_name in columns_to_update
        }
        if "updated_at" in valid_columns:
            update_values["updated_at"] = func.now()
        statement = statement.on_conflict_do_update(
            index_elements=[table.c[name] for name in conflict_columns],
            set_=update_values,
        )
        session.execute(statement)
        # psycopg는 INSERT .. ON CONFLICT batch의 rowcount를 -1로 돌려줄 수 있다.
        # 실제 transaction 성공 여부는 session이 관리하므로 여기서는 시도한 row 수를 반환한다.
        affected += len(batch)
    return affected


def upsert_dataframe(
    session: Session,
    model: type,
    frame: pd.DataFrame,
    *,
    conflict_columns: Sequence[str],
    column_mapping: dict[str, str] | None = None,
    update_columns: Sequence[str] | None = None,
    chunk_size: int = 1_000,
) -> int:
    """입력 컬럼명을 ORM 컬럼에 맞춘 뒤 DataFrame 전체를 공통 UPSERT 경로로 적재한다."""

    if frame.empty:
        return 0
    normalized = frame.rename(columns=column_mapping or {})
    return upsert_rows(
        session,
        model,
        dataframe_records(normalized),
        conflict_columns=conflict_columns,
        update_columns=update_columns,
        chunk_size=chunk_size,
    )
