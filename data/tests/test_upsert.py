from datetime import date

import pandas as pd
from sqlalchemy.dialects import postgresql

from db.models import StockMaster
from loaders.upsert import dataframe_records, upsert_rows


class _Result:
    rowcount = 1


class _Session:
    def __init__(self) -> None:
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return _Result()


def test_dataframe_records_converts_nat_and_timestamp() -> None:
    records = dataframe_records(
        pd.DataFrame(
            [
                {
                    "reference_date": pd.Timestamp("2026-08-13"),
                    "optional": pd.NaT,
                }
            ]
        )
    )
    assert records == [{"reference_date": date(2026, 8, 13), "optional": None}]


def test_upsert_compiles_on_conflict() -> None:
    session = _Session()
    affected = upsert_rows(
        session,
        StockMaster,
        [
            {
                "reference_date": date(2026, 8, 13),
                "stock_code": "005930",
                "market_type": "KOSPI",
                "stock_name": "삼성전자",
            }
        ],
        conflict_columns=["stock_code"],
    )
    sql = str(
        session.statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}
        )
    )
    assert affected == 1
    assert "ON CONFLICT (stock_code) DO UPDATE" in sql
    assert "updated_at = now()" in sql


def test_upsert_rejects_unknown_columns() -> None:
    session = _Session()
    try:
        upsert_rows(
            session,
            StockMaster,
            [{"stock_code": "005930", "unknown": "value"}],
            conflict_columns=["stock_code"],
        )
    except ValueError as error:
        assert "Unknown columns" in str(error)
    else:
        raise AssertionError("unknown columns must fail before executing SQL")
