"""리밸런싱 판단 proposal key 마이그레이션을 PostgreSQL에서 검증한다."""

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

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
PREVIOUS_REVISION = "20260828_0029"
HEAD_REVISION = "20260829_0033"


def _alembic_config() -> Config:
    config = Config(str(DATA_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(DATA_ROOT / "db" / "migrations"))
    return config


@pytest.fixture
def migration_database() -> Iterator[tuple[Config, Engine]]:
    config = _alembic_config()
    engine = build_engine()
    command.upgrade(config, HEAD_REVISION)
    command.downgrade(config, PREVIOUS_REVISION)
    try:
        yield config, engine
    finally:
        command.upgrade(config, HEAD_REVISION)
        engine.dispose()


def test_upgrade_backfills_key_and_removes_legacy_duplicates(
    migration_database: tuple[Config, Engine],
) -> None:
    config, engine = migration_database
    suffix = uuid4().hex[:8]
    account_id = uuid4()
    first_id = uuid4()
    duplicate_id = uuid4()

    with engine.begin() as connection:
        user_id = connection.scalar(
            text("""
                INSERT INTO users (
                    user_id, password_hash, name, birthdate, phone_number,
                    phone_verified_at, email, email_verified_at
                ) VALUES (
                    :login_id, 'migration-test-hash', '마이그레이션', '900101',
                    '01012345678', now(), :email, now()
                ) RETURNING id
                """),
            {
                "login_id": f"decision{suffix}",
                "email": f"decision{suffix}@example.com",
            },
        )
        connection.execute(
            text("""
                INSERT INTO virtual_accounts (
                    id, user_id, operation_mode, account_name,
                    initial_cash, cash_balance, status, selected_strategy_id
                ) VALUES (
                    :id, :user_id, 'SEMI_AUTO', 'migration account',
                    1000000, 1000000, 'ACTIVE', 'low'
                )
                """),
            {"id": account_id, "user_id": user_id},
        )
        for decision_id, decision, key, created_at in (
            (first_id, "ACCEPTED", "legacy-first", "2026-08-25T01:00:00+00:00"),
            (duplicate_id, "HELD", "legacy-second", "2026-08-25T02:00:00+00:00"),
        ):
            connection.execute(
                text("""
                    INSERT INTO rebalancing_decisions (
                        id, account_id, strategy_id, stock_code, stock_name,
                        action, current_weight, target_weight, weight_diff,
                        recommended_amount, decision, idempotency_key,
                        baseline_snapshot_date, baseline_total_assets, created_at
                    ) VALUES (
                        :id, :account_id, 'low', '005930', '삼성전자',
                        'SELL', 20, 15, 5, 50000, :decision, :key,
                        '2026-08-25', 1000000, :created_at
                    )
                    """),
                {
                    "id": decision_id,
                    "account_id": account_id,
                    "decision": decision,
                    "key": key,
                    "created_at": created_at,
                },
            )

    command.upgrade(config, HEAD_REVISION)

    with engine.connect() as connection:
        rows = (
            connection.execute(
                text("""
                SELECT id, decision, proposal_key
                FROM rebalancing_decisions
                WHERE account_id = :account_id
                """),
                {"account_id": account_id},
            )
            .mappings()
            .all()
        )

    assert len(rows) == 1
    assert rows[0]["id"] == first_id
    assert rows[0]["decision"] == "ACCEPTED"
    assert (
        rows[0]["proposal_key"]
        == "low|005930|SELL|20.00|15.00|5.00|50000.00|2026-08-25"
    )
    columns = {
        column["name"]: column
        for column in inspect(engine).get_columns("rebalancing_decisions")
    }
    assert columns["proposal_key"]["nullable"] is False
    unique_constraints = {
        constraint["name"]
        for constraint in inspect(engine).get_unique_constraints(
            "rebalancing_decisions"
        )
    }
    assert "uq_rebalancing_decisions_account_proposal" in unique_constraints

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM virtual_accounts WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        connection.execute(
            text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id}
        )
