"""Verify PostgreSQL connectivity and report managed schemas/tables."""

from sqlalchemy import inspect, text

from db.connection import build_engine


def main() -> None:
    engine = build_engine()
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version()")).scalar_one()
    inspector = inspect(engine)
    print(f"connection: ok ({version.split(',')[0]})")
    for schema in ("raw", "processed"):
        tables = inspector.get_table_names(schema=schema)
        print(f"{schema}: {', '.join(tables) if tables else '(empty)'}")


if __name__ == "__main__":
    main()
