"""운용방식별 가상계좌 migration의 PostgreSQL 경계를 검증한다."""

import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import DBAPIError

from db.connection import build_engine


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MIGRATION_INTEGRATION") != "1",
    reason="RUN_MIGRATION_INTEGRATION=1 required",
)

DATA_ROOT = Path(__file__).resolve().parents[1]
HEAD_REVISION = "20260826_0022"
ACTIVE_OPERATION_MODE_PREVIOUS_REVISION = "20260825_0020"
PREVIOUS_REVISION = "20260825_0019"


def _alembic_config() -> Config:
    config = Config(str(DATA_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(DATA_ROOT / "db" / "migrations"))
    return config


@pytest.fixture(scope="module")
def migration_database() -> Iterator[tuple[Config, Engine]]:
    """CI 전용 PostgreSQL을 head로 준비하고 테스트 종료 후에도 head를 보장한다."""

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


def _insert_user(engine: Engine) -> tuple[int, str]:
    suffix = uuid4().hex[:10]
    login_id = f"mig{suffix}"
    with engine.begin() as connection:
        user_id = connection.scalar(
            text(
                """
                INSERT INTO users (
                    user_id, password_hash, name, birthdate, phone_number,
                    phone_verified_at, email, email_verified_at
                )
                VALUES (
                    :login_id, 'migration-test-hash', '마이그레이션', '900101',
                    '01012345678', now(), :email, now()
                )
                RETURNING id
                """
            ),
            {"login_id": login_id, "email": f"{login_id}@example.com"},
        )
    assert isinstance(user_id, int)
    return user_id, login_id


def _insert_account(
    engine: Engine,
    user_id: int,
    operation_mode: str,
    *,
    initial_cash: int = 100,
    status: str = "ACTIVE",
) -> UUID:
    account_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO virtual_accounts (
                    id, user_id, operation_mode, account_name,
                    initial_cash, cash_balance, status
                )
                VALUES (
                    :id, :user_id, :operation_mode, :account_name,
                    :initial_cash, :initial_cash, :status
                )
                """
            ),
            {
                "id": account_id,
                "user_id": user_id,
                "operation_mode": operation_mode,
                "account_name": f"{operation_mode} 테스트 계좌",
                "initial_cash": initial_cash,
                "status": status,
            },
        )
    return account_id


def _insert_onboarding(
    engine: Engine,
    user_id: int,
    operation_mode: str,
    *,
    account_id: UUID | None = None,
    status: str | None = None,
    completed_at: datetime | None = None,
) -> UUID:
    onboarding_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO investment_onboardings (
                    id, user_id, strategy_id, investment_amount,
                    operation_mode, status, account_id, completed_at
                )
                VALUES (
                    :id, :user_id, 'low', 100, :operation_mode,
                    :status, :account_id, :completed_at
                )
                """
            ),
            {
                "id": onboarding_id,
                "user_id": user_id,
                "operation_mode": operation_mode,
                "status": status or ("READY" if account_id else "ACCOUNT_PENDING"),
                "account_id": account_id,
                "completed_at": completed_at,
            },
        )
    return onboarding_id


def _seed_incompatible_state(engine: Engine, case: str) -> str:
    user_id, login_id = _insert_user(engine)
    if case == "multiple_accounts":
        _insert_account(engine, user_id, "AUTO")
        _insert_account(engine, user_id, "SEMI_AUTO")
    elif case == "multiple_onboardings":
        _insert_onboarding(engine, user_id, "AUTO")
        _insert_onboarding(engine, user_id, "SEMI_AUTO")
    elif case == "empty_account":
        _insert_account(engine, user_id, "AUTO", initial_cash=0)
    elif case == "account_deposit":
        account_id = _insert_account(engine, user_id, "AUTO")
        onboarding_id = _insert_onboarding(
            engine,
            user_id,
            "AUTO",
            account_id=account_id,
        )
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO account_deposits (
                        id, account_id, onboarding_id, amount,
                        balance_after, status, idempotency_key
                    )
                    VALUES (
                        :id, :account_id, :onboarding_id, 100,
                        100, 'COMPLETED', :idempotency_key
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "account_id": account_id,
                    "onboarding_id": onboarding_id,
                    "idempotency_key": f"migration-{uuid4().hex}",
                },
            )
    elif case == "deposit_ledger":
        account_id = _insert_account(engine, user_id, "AUTO")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO cash_ledger (
                        account_id, transaction_type, amount,
                        balance_after, reference_type, reference_id
                    )
                    VALUES (
                        :account_id, 'DEPOSIT', 100, 100,
                        'DEPOSIT', :reference_id
                    )
                    """
                ),
                {"account_id": account_id, "reference_id": uuid4().hex},
            )
    else:
        raise AssertionError(f"unknown migration test case: {case}")
    return login_id


def _delete_test_user(engine: Engine, login_id: str) -> None:
    """FK 순서대로 해당 테스트가 만든 행만 제거한다."""

    with engine.begin() as connection:
        user_id = connection.scalar(
            text("SELECT id FROM users WHERE user_id = :login_id"),
            {"login_id": login_id},
        )
        if user_id is None:
            return
        connection.execute(
            text(
                """
                DELETE FROM account_deposits
                WHERE onboarding_id IN (
                    SELECT id FROM investment_onboardings WHERE user_id = :user_id
                )
                """
            ),
            {"user_id": user_id},
        )
        connection.execute(
            text("DELETE FROM investment_onboardings WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        connection.execute(
            text(
                """
                DELETE FROM cash_ledger
                WHERE account_id IN (
                    SELECT id FROM virtual_accounts WHERE user_id = :user_id
                )
                """
            ),
            {"user_id": user_id},
        )
        connection.execute(
            text("DELETE FROM virtual_accounts WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        connection.execute(
            text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )


def test_empty_feature_state_can_downgrade_and_upgrade(
    migration_database: tuple[Config, Engine],
) -> None:
    config, engine = migration_database

    command.downgrade(config, PREVIOUS_REVISION)
    try:
        assert _current_revision(engine) == PREVIOUS_REVISION
        assert "operation_mode" not in {
            column["name"] for column in inspect(engine).get_columns("virtual_accounts")
        }
    finally:
        command.upgrade(config, HEAD_REVISION)

    assert _current_revision(engine) == HEAD_REVISION


def test_active_mode_backfill_ignores_completed_onboarding_for_suspended_account(
    migration_database: tuple[Config, Engine],
) -> None:
    config, engine = migration_database
    command.downgrade(config, ACTIVE_OPERATION_MODE_PREVIOUS_REVISION)
    user_id, login_id = _insert_user(engine)
    _insert_account(engine, user_id, "AUTO")
    suspended_account_id = _insert_account(
        engine,
        user_id,
        "SEMI_AUTO",
        status="SUSPENDED",
    )
    _insert_onboarding(
        engine,
        user_id,
        "SEMI_AUTO",
        account_id=suspended_account_id,
        status="COMPLETED",
        completed_at=datetime(2026, 8, 25, tzinfo=UTC),
    )

    try:
        command.upgrade(config, HEAD_REVISION)
        with engine.connect() as connection:
            active_operation_mode = connection.scalar(
                text("SELECT active_operation_mode FROM users WHERE id = :user_id"),
                {"user_id": user_id},
            )

        # SUSPENDED 계좌의 완료 이력은 제외되고, 유일한 ACTIVE 계좌로 복원되어야 한다.
        assert active_operation_mode == "AUTO"
    finally:
        command.upgrade(config, HEAD_REVISION)
        _delete_test_user(engine, login_id)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("multiple_accounts", "a user has multiple operation-mode accounts"),
        ("multiple_onboardings", "a user has multiple operation-mode onboardings"),
        ("empty_account", "virtual_accounts contains non-positive initial_cash"),
        ("account_deposit", "account_deposits contains feature data"),
        ("deposit_ledger", "cash_ledger contains DEPOSIT rows"),
    ],
)
def test_incompatible_feature_state_blocks_downgrade_before_schema_changes(
    migration_database: tuple[Config, Engine],
    case: str,
    message: str,
) -> None:
    config, engine = migration_database
    command.upgrade(config, HEAD_REVISION)
    login_id = _seed_incompatible_state(engine, case)

    try:
        with pytest.raises(DBAPIError, match=re.escape(message)):
            command.downgrade(config, PREVIOUS_REVISION)

        assert _current_revision(engine) == HEAD_REVISION
        assert "operation_mode" in {
            column["name"] for column in inspect(engine).get_columns("virtual_accounts")
        }
        assert inspect(engine).has_table("account_deposits")
    finally:
        _delete_test_user(engine, login_id)
