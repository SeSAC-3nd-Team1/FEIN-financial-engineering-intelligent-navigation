"""Verify PostgreSQL connectivity and show the persistent membership state."""

from sqlalchemy import inspect, text

from db.connection import build_engine


MEMBERSHIP_TABLES = ("users", "terms", "user_agreements")


def main() -> None:
    engine = build_engine()
    inspector = inspect(engine)
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version()")).scalar_one()
        print(f"connection: ok ({version.split(',')[0]})")
        public_tables = set(inspector.get_table_names(schema="public"))
        for table in MEMBERSHIP_TABLES:
            if table not in public_tables:
                print(f"public.{table}: missing")
                continue
            count = connection.scalar(text(f'SELECT count(*) FROM public."{table}"'))
            print(f"public.{table}: rows={count}")
        user_schemas = [
            schema
            for schema in inspector.get_schema_names()
            if schema not in {"information_schema", "pg_catalog", "pg_toast"}
            and not schema.startswith("pg_")
        ]
        print(f"schemas: {', '.join(sorted(user_schemas))}")


if __name__ == "__main__":
    main()
