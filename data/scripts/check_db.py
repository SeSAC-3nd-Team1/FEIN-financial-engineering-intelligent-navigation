"""PostgreSQL 연결과 현재 영구 보존 membership 상태를 빠르게 확인한다."""

from sqlalchemy import inspect, text

from db.connection import build_engine


MEMBERSHIP_TABLES = ("users", "terms", "user_agreements")


def main() -> None:
    """연결 가능 여부, membership row 수, 사용자 schema 목록을 출력한다.

    금융/API schema가 retire된 이후에도 보호 대상 public table이 남아 있는지 운영자가
    파괴적 migration 전후에 간단히 확인할 수 있도록 하는 진단용 script다.
    """

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

        # PostgreSQL 내부 system schema는 제외해 프로젝트가 관리하는 schema만 보여준다.
        user_schemas = [
            schema
            for schema in inspector.get_schema_names()
            if schema not in {"information_schema", "pg_catalog", "pg_toast"}
            and not schema.startswith("pg_")
        ]
        print(f"schemas: {', '.join(sorted(user_schemas))}")


if __name__ == "__main__":
    main()
