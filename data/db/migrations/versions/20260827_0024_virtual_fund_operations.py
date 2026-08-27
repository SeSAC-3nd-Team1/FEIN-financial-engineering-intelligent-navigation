"""내부 가상계좌의 추가투자·출금과 현재 투자원금을 추가한다.

Revision ID: 20260827_0024
Revises: 20260826_0023
Create Date: 2026-08-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260827_0024"
down_revision: str | None = "20260826_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """기존 원장을 보존하면서 가상 자금 작업을 원자적으로 기록할 구조를 만든다."""

    op.add_column(
        "virtual_accounts",
        sa.Column(
            "invested_principal",
            sa.Numeric(20, 2),
            server_default="0",
            nullable=True,
        ),
    )
    # 최초 입금 원장이 없는 데모·레거시 계좌는 initial_cash를 사용하고, 원장이 있는
    # 계좌는 외부 현금 유입 합계로 복원해 첫 입금을 이중 계산하지 않는다.
    op.execute(
        """
        UPDATE virtual_accounts AS account
        SET invested_principal = GREATEST(0, COALESCE(
            (
                SELECT SUM(ledger.amount)
                FROM cash_ledger AS ledger
                WHERE ledger.account_id = account.id
                  AND ledger.transaction_type IN ('INITIAL_DEPOSIT', 'DEPOSIT', 'ADJUSTMENT')
            ),
            account.initial_cash,
            0
        ))
        """
    )
    op.alter_column(
        "virtual_accounts",
        "invested_principal",
        existing_type=sa.Numeric(20, 2),
        nullable=False,
        server_default="0",
    )
    op.create_check_constraint(
        "invested_principal_nonnegative",
        "virtual_accounts",
        "invested_principal >= 0",
    )

    op.drop_constraint("ck_cash_ledger_type_values", "cash_ledger", type_="check")
    op.create_check_constraint(
        "type_values",
        "cash_ledger",
        "transaction_type IN ("
        "'INITIAL_DEPOSIT', 'DEPOSIT', 'ADDITIONAL_INVESTMENT', "
        "'WITHDRAWAL', 'BUY', 'SELL', 'ADJUSTMENT'"
        ")",
    )

    op.create_table(
        "fund_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("requested_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("executed_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("principal_before", sa.Numeric(20, 2), nullable=False),
        sa.Column("principal_after", sa.Numeric(20, 2), nullable=False),
        sa.Column("total_assets_before", sa.Numeric(20, 2), nullable=False),
        sa.Column("total_assets_after", sa.Numeric(20, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"], ["virtual_accounts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="uq_fund_operations_account_idempotency",
        ),
        sa.CheckConstraint(
            "operation_type IN ('ADDITIONAL_INVESTMENT', 'WITHDRAWAL')",
            name="operation_type_values",
        ),
        sa.CheckConstraint(
            "status IN ('PROCESSING', 'COMPLETED', 'FAILED')",
            name="status_values",
        ),
        sa.CheckConstraint("requested_amount > 0", name="requested_amount_positive"),
        sa.CheckConstraint("executed_amount >= 0", name="executed_amount_nonnegative"),
        sa.CheckConstraint(
            "principal_before >= 0 AND principal_after >= 0",
            name="principal_nonnegative",
        ),
        sa.CheckConstraint(
            "total_assets_before >= 0 AND total_assets_after >= 0",
            name="total_assets_nonnegative",
        ),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED')",
            name="completion_consistency",
        ),
    )
    op.create_index(
        "ix_fund_operations_account_created",
        "fund_operations",
        ["account_id", "created_at"],
    )

    op.create_table(
        "fund_operation_orders",
        sa.Column("fund_operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("applied_weight", sa.Numeric(9, 8), nullable=False),
        sa.ForeignKeyConstraint(
            ["fund_operation_id"], ["fund_operations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("fund_operation_id", "order_id"),
        sa.UniqueConstraint("order_id", name="uq_fund_operation_orders_order_id"),
        sa.CheckConstraint("allocated_amount > 0", name="allocated_amount_positive"),
        sa.CheckConstraint(
            "applied_weight >= 0 AND applied_weight <= 1",
            name="applied_weight_range",
        ),
    )


def downgrade() -> None:
    """가상 자금 작업 이력이 있으면 감사 데이터를 잃지 않도록 중단한다."""

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM fund_operations) THEN
                RAISE EXCEPTION
                    '20260827_0024 downgrade blocked: fund_operations contains feature data';
            END IF;
        END $$
        """
    )
    op.drop_table("fund_operation_orders")
    op.drop_index("ix_fund_operations_account_created", table_name="fund_operations")
    op.drop_table("fund_operations")
    op.drop_constraint("ck_cash_ledger_type_values", "cash_ledger", type_="check")
    op.create_check_constraint(
        "type_values",
        "cash_ledger",
        "transaction_type IN ("
        "'INITIAL_DEPOSIT', 'DEPOSIT', 'BUY', 'SELL', 'ADJUSTMENT'"
        ")",
    )
    op.drop_constraint(
        "ck_virtual_accounts_invested_principal_nonnegative",
        "virtual_accounts",
        type_="check",
    )
    op.drop_column("virtual_accounts", "invested_principal")
