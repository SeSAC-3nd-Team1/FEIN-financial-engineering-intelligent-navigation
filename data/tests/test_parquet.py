from pathlib import Path

from sqlalchemy import create_engine, text

from transforms.parquet import export_query_to_parquet


def test_export_query_to_parquet(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE prices (stock_code TEXT, close_price INT)"))
        connection.execute(
            text("INSERT INTO prices VALUES ('005930', 80700), ('000660', 210000)")
        )
    output = export_query_to_parquet(
        engine,
        text("SELECT * FROM prices ORDER BY stock_code"),
        tmp_path / "nested" / "prices.parquet",
    )
    assert output.exists()
    assert output.stat().st_size > 0
