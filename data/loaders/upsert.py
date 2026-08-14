"""Chunked PostgreSQL UPSERT utilities for rows and pandas DataFrames."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import pandas as pd
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


IMMUTABLE_COLUMNS = {"created_at"}


def _chunks(rows: Sequence[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield list(rows[start : start + size])


def _python_value(value: Any) -> Any:
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
    """Convert pandas/numpy scalar values to DBAPI-compatible Python values."""

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
    """UPSERT rows with PostgreSQL ``ON CONFLICT DO UPDATE``.

    ``conflict_columns`` must match a primary key or UNIQUE constraint. By default,
    all supplied non-key columns except creation timestamps are refreshed.
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

    # PostgreSQL cannot update the same conflict key twice in one INSERT.
    # Some public APIs return exact duplicate items within a single page.
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
        # psycopg may report -1 for INSERT .. ON CONFLICT batches; attempted rows
        # are deterministic and the transaction still controls final persistence.
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
    """Rename source columns and UPSERT a DataFrame into a mapped ORM table."""

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
