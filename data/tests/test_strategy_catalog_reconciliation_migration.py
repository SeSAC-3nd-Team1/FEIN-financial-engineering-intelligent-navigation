"""전략 카탈로그 스키마 드리프트 복구 migration을 PostgreSQL에서 검증한다."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

from db.connection import build_engine


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MIGRATION_INTEGRATION") != "1",
    reason="RUN_MIGRATION_INTEGRATION=1 required",
)

DATA_ROOT = Path(__file__).resolve().parents[1]
PRE_STRATEGY_REVISION = "20260827_0024"
SKIPPED_STRATEGY_REVISION = "20260828_0025"
DRIFTED_REVISION = "20260828_0026"
HEAD_REVISION = "20260828_0028"
STRATEGY_COLUMNS = {
    "product_group",
    "availability_status",
    "engine_key",
    "display_order",
}


def _alembic_config() -> Config:
    config = Config(str(DATA_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(DATA_ROOT / "db" / "migrations"))
    return config


@pytest.fixture(scope="module")
def migration_database() -> Iterator[tuple[Config, Engine]]:
    """CI 전용 PostgreSQL을 사용하고 테스트 종료 시 최신 revision을 보장한다."""

    config = _alembic_config()
    engine = build_engine()
    command.upgrade(config, HEAD_REVISION)
    try:
        yield config, engine
    finally:
        command.upgrade(config, HEAD_REVISION)
        engine.dispose()


def _current_revision(engine: Engine) -> str:
    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert isinstance(revision, str)
    return revision


def test_reconciliation_repairs_revision_only_strategy_migration(
    migration_database: tuple[Config, Engine],
) -> None:
    """0025 DDL 없이 revision만 진행된 DB를 0027이 안전하게 복구해야 한다."""

    config, engine = migration_database
    command.downgrade(config, PRE_STRATEGY_REVISION)

    # 실제 장애처럼 0025의 upgrade를 실행하지 않고 revision만 기록한 다음,
    # 독립 입금 테이블을 추가한 0026은 정상 적용한다.
    command.stamp(config, SKIPPED_STRATEGY_REVISION)
    command.upgrade(config, DRIFTED_REVISION)

    drifted_columns = {
        column["name"] for column in inspect(engine).get_columns("strategies")
    }
    assert _current_revision(engine) == DRIFTED_REVISION
    assert STRATEGY_COLUMNS.isdisjoint(drifted_columns)
    assert inspect(engine).has_table("account_cash_deposits")

    command.upgrade(config, HEAD_REVISION)

    strategy_inspector = inspect(engine)
    repaired_columns = {
        column["name"]: column
        for column in strategy_inspector.get_columns("strategies")
    }
    assert _current_revision(engine) == HEAD_REVISION
    assert STRATEGY_COLUMNS <= repaired_columns.keys()
    assert all(not repaired_columns[name]["nullable"] for name in STRATEGY_COLUMNS)

    constraint_names = {
        constraint["name"]
        for constraint in strategy_inspector.get_check_constraints("strategies")
    }
    assert {
        "ck_strategies_product_group_values",
        "ck_strategies_availability_status_values",
        "ck_strategies_display_order_positive",
    } <= constraint_names
    assert "ix_strategies_catalog_order" in {
        index["name"] for index in strategy_inspector.get_indexes("strategies")
    }
    assessment_columns = {
        column["name"]: column
        for column in strategy_inspector.get_columns("investor_profile_assessments")
    }
    assert assessment_columns["risk_score"]["nullable"] is True
    assessment_constraints = {
        constraint["name"]
        for constraint in strategy_inspector.get_check_constraints("investor_profile_assessments")
    }
    assert "ck_investor_profile_assessments_risk_score_range" in assessment_constraints

    with engine.connect() as connection:
        momentum = connection.execute(
            text(
                """
                SELECT product_group, availability_status, engine_key, display_order
                FROM strategies
                WHERE id = 'momentum'
                """
            )
        ).mappings().one()
        strategy_ids = set(connection.scalars(text("SELECT id FROM strategies")))

    assert dict(momentum) == {
        "product_group": "BANG",
        "availability_status": "AVAILABLE",
        "engine_key": "price_momentum_v1",
        "display_order": 10,
    }
    assert {"low", "value", "momentum", "stat_arb", "event_driven"} <= strategy_ids

    # 복구 후 ORM metadata와 새 DB schema 사이에 추가 DDL 차이가 없어야 한다.
    command.check(config)
