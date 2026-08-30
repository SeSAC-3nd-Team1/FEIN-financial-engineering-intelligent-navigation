from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.dialects import postgresql

from db.models import Term
from loaders.upsert import dataframe_records, upsert_rows


class _Result:
    rowcount = 1


class _Session:
    def __init__(self) -> None:
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return _Result()


def _term_row(title: str = "서비스 이용약관") -> dict:
    return {
        "term_code": "SERVICE",
        "version": "1.0",
        "title": title,
        "is_required": True,
        "effective_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
    }


def test_dataframe_records_converts_nat_and_timestamp() -> None:
    records = dataframe_records(pd.DataFrame([{"at": pd.Timestamp("2026-08-13"), "optional": pd.NaT}]))
    assert records[0]["at"].isoformat() == "2026-08-13"
    assert records[0]["optional"] is None


def test_upsert_compiles_on_conflict() -> None:
    session = _Session()
    affected = upsert_rows(
        session,
        Term,
        [_term_row()],
        conflict_columns=["term_code", "version"],
    )
    sql = str(session.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}))
    assert affected == 1
    assert "ON CONFLICT (term_code, version) DO UPDATE" in sql


def test_upsert_rejects_unknown_columns() -> None:
    session = _Session()
    try:
        upsert_rows(
            session,
            Term,
            [{**_term_row(), "unknown": "value"}],
            conflict_columns=["term_code", "version"],
        )
    except ValueError as error:
        assert "Unknown columns" in str(error)
    else:
        raise AssertionError("unknown columns must fail before executing SQL")


def test_upsert_deduplicates_conflict_keys_within_batch() -> None:
    session = _Session()
    affected = upsert_rows(
        session,
        Term,
        [_term_row("old"), _term_row("new")],
        conflict_columns=["term_code", "version"],
    )
    assert affected == 1
