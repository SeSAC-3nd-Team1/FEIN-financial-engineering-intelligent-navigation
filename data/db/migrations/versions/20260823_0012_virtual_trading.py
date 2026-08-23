"""내부 가상투자 계좌·주문·체결·원장 schema를 추가한다.

Revision ID: 20260823_0012
Revises: 20260816_0011
Create Date: 2026-08-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0012"
down_revision: str | None = "20260816_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(30), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("rebalance_cycle", sa.String(30), nullable=False),
        sa.Column("rule_config", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("risk_level IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_strategies_risk_level_values"),
    )
    op.execute("""
        INSERT INTO strategies (id, name, description, risk_level, rebalance_cycle, rule_config)
        VALUES
          ('low', '저변동성 전략', '큰 손실을 줄이고 꾸준한 투자를 지향합니다.', 'MEDIUM', 'MONTHLY', '{"factor":"low_volatility"}'),
          ('value', '가치 전략', '가격 대비 기업가치가 우수한 종목을 선택합니다.', 'MEDIUM', 'QUARTERLY', '{"factor":"value"}'),
          ('momentum', '모멘텀 전략', '최근 상승 흐름이 강한 종목을 선택합니다.', 'HIGH', 'MONTHLY', '{"factor":"momentum"}')
    """)

    op.create_table(
        "virtual_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("account_name", sa.String(100), nullable=False),
        sa.Column("initial_cash", sa.Numeric(20, 2), nullable=False),
        sa.Column("cash_balance", sa.Numeric(20, 2), nullable=False),
        sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
        sa.Column("selected_strategy_id", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["selected_strategy_id"], ["strategies.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", name="uq_virtual_accounts_user_id"),
        sa.CheckConstraint("initial_cash > 0", name="ck_virtual_accounts_initial_cash_positive"),
        sa.CheckConstraint("cash_balance >= 0", name="ck_virtual_accounts_cash_balance_nonnegative"),
        sa.CheckConstraint("status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')", name="ck_virtual_accounts_status_values"),
    )
    op.create_index("ix_virtual_accounts_status", "virtual_accounts", ["status"])

    op.create_table(
        "positions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stock_code", sa.String(12), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("average_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("realized_profit", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["virtual_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("account_id", "stock_code", name="uq_positions_account_stock"),
        sa.CheckConstraint("quantity >= 0", name="ck_positions_quantity_nonnegative"),
        sa.CheckConstraint("average_price > 0", name="ck_positions_average_price_positive"),
    )
    op.create_index("ix_positions_account_id", "positions", ["account_id"])

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stock_code", sa.String(12), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("order_type", sa.String(10), server_default="MARKET", nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("requested_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("rejection_code", sa.String(50), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["virtual_accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_orders_account_idempotency"),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_orders_side_values"),
        sa.CheckConstraint("order_type = 'MARKET'", name="ck_orders_market_only"),
        sa.CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),
        sa.CheckConstraint("status IN ('PENDING', 'FILLED', 'REJECTED', 'CANCELLED')", name="ck_orders_status_values"),
    )
    op.create_index("ix_orders_account_requested_at", "orders", ["account_id", "requested_at"])

    op.create_table(
        "executions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stock_code", sa.String(12), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("execution_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["account_id"], ["virtual_accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("order_id", name="uq_executions_order_id"),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_executions_side_values"),
        sa.CheckConstraint("quantity > 0", name="ck_executions_quantity_positive"),
        sa.CheckConstraint("execution_price > 0", name="ck_executions_price_positive"),
    )
    op.create_index("ix_executions_account_executed_at", "executions", ["account_id", "executed_at"])

    op.create_table(
        "cash_ledger",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(20, 2), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=False),
        sa.Column("reference_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["virtual_accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("transaction_type IN ('INITIAL_DEPOSIT', 'BUY', 'SELL', 'ADJUSTMENT')", name="ck_cash_ledger_type_values"),
        sa.CheckConstraint("amount <> 0", name="ck_cash_ledger_amount_nonzero"),
        sa.CheckConstraint("balance_after >= 0", name="ck_cash_ledger_balance_nonnegative"),
    )
    op.create_index("ix_cash_ledger_account_created_at", "cash_ledger", ["account_id", "created_at"])
    op.create_index("ix_cash_ledger_reference", "cash_ledger", ["reference_type", "reference_id"])


def downgrade() -> None:
    op.drop_table("cash_ledger")
    op.drop_table("executions")
    op.drop_table("orders")
    op.drop_table("positions")
    op.drop_table("virtual_accounts")
    op.drop_table("strategies")
