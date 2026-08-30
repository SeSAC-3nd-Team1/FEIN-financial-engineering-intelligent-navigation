"""전략 카탈로그 마이그레이션의 raw SQL 컴파일 계약을 검증한다."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "versions"
    / "20260828_0025_strategy_catalog_refactor.py"
)


class RecordingOperations:
    """DB 변경 대신 upgrade의 raw SQL만 수집하는 검증용 연산자다."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement) -> None:
        self.statements.append(str(statement))

    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


def _migration_module():
    spec = spec_from_file_location("strategy_catalog_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_raw_sql_has_no_unbound_parameters() -> None:
    """JSON의 colon+숫자가 SQLAlchemy bind parameter로 파싱되지 않아야 한다."""

    migration = _migration_module()
    operations = RecordingOperations()
    migration.op = operations

    migration.upgrade()

    assert operations.statements
    for statement in operations.statements:
        compiled = sa.text(statement).compile(dialect=postgresql.dialect())
        assert compiled.params == {}, statement
