"""운용방식별 가상계좌와 부족분 1회 입금 이력을 추가한다.

Revision ID: 20260825_0020
Revises: 20260825_0019
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260825_0020"
down_revision: str | None = "20260825_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "virtual_accounts",
        sa.Column("operation_mode", sa.String(20), nullable=True),
    )
    # 기존 단일 계좌는 연결된 온보딩의 운용방식을 우선 보존한다. 연결 정보가 없는 레거시
    # 계좌는 과거 프런트 기본 운용방식이던 반자동으로 귀속해 마이그레이션을 결정적으로 만든다.
    op.execute("""
        UPDATE virtual_accounts AS account
        SET operation_mode = COALESCE(
            (
                SELECT onboarding.operation_mode
                FROM investment_onboardings AS onboarding
                WHERE onboarding.account_id = account.id
                ORDER BY onboarding.updated_at DESC, onboarding.created_at DESC
                LIMIT 1
            ),
            'SEMI_AUTO'
        )
    """)
    op.alter_column("virtual_accounts", "operation_mode", nullable=False)
    op.drop_constraint("uq_virtual_accounts_user_id", "virtual_accounts", type_="unique")
    op.create_unique_constraint(
        "uq_virtual_accounts_user_mode",
        "virtual_accounts",
        ["user_id", "operation_mode"],
    )
    op.create_check_constraint(
        "operation_mode_values",
        "virtual_accounts",
        "operation_mode IN ('AUTO', 'SEMI_AUTO')",
    )
    op.drop_constraint(
        "ck_virtual_accounts_initial_cash_positive",
        "virtual_accounts",
        type_="check",
    )
    op.create_check_constraint(
        "initial_cash_nonnegative",
        "virtual_accounts",
        "initial_cash >= 0",
    )

    op.drop_constraint(
        "uq_investment_onboardings_user_id",
        "investment_onboardings",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_investment_onboardings_user_mode",
        "investment_onboardings",
        ["user_id", "operation_mode"],
    )
    op.drop_constraint(
        "ck_investment_onboardings_status_values",
        "investment_onboardings",
        type_="check",
    )
    op.create_check_constraint(
        "status_values",
        "investment_onboardings",
        "status IN ('TERMS_PENDING', 'ACCOUNT_PENDING', 'DEPOSIT_PENDING', 'READY', 'COMPLETED')",
    )

    op.drop_constraint("ck_cash_ledger_type_values", "cash_ledger", type_="check")
    op.create_check_constraint(
        "type_values",
        "cash_ledger",
        "transaction_type IN ('INITIAL_DEPOSIT', 'DEPOSIT', 'BUY', 'SELL', 'ADJUSTMENT')",
    )

    op.create_table(
        "account_deposits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("onboarding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(20, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["virtual_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["onboarding_id"], ["investment_onboardings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="uq_account_deposits_account_idempotency",
        ),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.CheckConstraint("balance_after >= 0", name="balance_nonnegative"),
        sa.CheckConstraint("status = 'COMPLETED'", name="status_values"),
    )
    op.create_index(
        "ix_account_deposits_account_created",
        "account_deposits",
        ["account_id", "created_at"],
    )


def downgrade() -> None:
    # 0019 스키마는 운용방식별 복수 계좌, 0원 준비 계좌, DEPOSIT 원장을 표현할 수 없다.
    # 거래 이력을 임의 삭제하거나 서로 다른 계좌를 병합하면 원장 정합성이 깨지므로,
    # 어떤 DDL도 실행하기 전에 비호환 데이터를 검증하고 명시적으로 중단한다.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM account_deposits) THEN
                RAISE EXCEPTION
                    '20260825_0020 downgrade blocked: account_deposits contains feature data; back up and migrate it explicitly';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM cash_ledger
                WHERE transaction_type = 'DEPOSIT'
            ) THEN
                RAISE EXCEPTION
                    '20260825_0020 downgrade blocked: cash_ledger contains DEPOSIT rows; back up and migrate them explicitly';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM virtual_accounts
                GROUP BY user_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    '20260825_0020 downgrade blocked: a user has multiple operation-mode accounts; choose one account explicitly';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM investment_onboardings
                GROUP BY user_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    '20260825_0020 downgrade blocked: a user has multiple operation-mode onboardings; choose one onboarding explicitly';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM virtual_accounts
                WHERE initial_cash <= 0
            ) THEN
                RAISE EXCEPTION
                    '20260825_0020 downgrade blocked: virtual_accounts contains non-positive initial_cash; resolve empty accounts explicitly';
            END IF;
        END;
        $$
        """
    )

    op.drop_index("ix_account_deposits_account_created", table_name="account_deposits")
    op.drop_table("account_deposits")

    op.drop_constraint("type_values", "cash_ledger", type_="check")
    op.create_check_constraint(
        "ck_cash_ledger_type_values",
        "cash_ledger",
        "transaction_type IN ('INITIAL_DEPOSIT', 'BUY', 'SELL', 'ADJUSTMENT')",
    )

    # 이전 revision에는 입금 대기 상태가 없으므로 계좌 준비가 끝난 상태로 축약한다.
    op.execute("UPDATE investment_onboardings SET status = 'READY' WHERE status = 'DEPOSIT_PENDING'")
    op.drop_constraint(
        "status_values",
        "investment_onboardings",
        type_="check",
    )
    op.create_check_constraint(
        "ck_investment_onboardings_status_values",
        "investment_onboardings",
        "status IN ('TERMS_PENDING', 'ACCOUNT_PENDING', 'READY', 'COMPLETED')",
    )
    op.drop_constraint(
        "uq_investment_onboardings_user_mode",
        "investment_onboardings",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_investment_onboardings_user_id",
        "investment_onboardings",
        ["user_id"],
    )

    op.drop_constraint(
        "initial_cash_nonnegative",
        "virtual_accounts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_virtual_accounts_initial_cash_positive",
        "virtual_accounts",
        "initial_cash > 0",
    )
    op.drop_constraint(
        "operation_mode_values",
        "virtual_accounts",
        type_="check",
    )
    op.drop_constraint(
        "uq_virtual_accounts_user_mode",
        "virtual_accounts",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_virtual_accounts_user_id",
        "virtual_accounts",
        ["user_id"],
    )
    op.drop_column("virtual_accounts", "operation_mode")
