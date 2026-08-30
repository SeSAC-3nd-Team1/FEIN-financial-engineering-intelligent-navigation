"""가상거래 주문·체결·보유수량에 소수점 매매를 허용한다.

Revision ID: 20260825_0019
Revises: 20260825_0018
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_0019"
down_revision: str | None = "20260825_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


QUANTITY_TABLES = ("positions", "orders", "executions")


def upgrade() -> None:
    """기존 정수 수량을 손실 없이 소수점 8자리 수량으로 확장한다."""

    for table in QUANTITY_TABLES:
        op.alter_column(
            table,
            "quantity",
            existing_type=sa.BigInteger(),
            type_=sa.Numeric(20, 8),
            existing_nullable=False,
            postgresql_using="quantity::numeric(20,8)",
        )


def downgrade() -> None:
    """소수점 보유가 있으면 손실 변환 대신 명시적으로 downgrade를 거부한다."""

    for table in QUANTITY_TABLES:
        op.execute(sa.text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM {table} WHERE quantity <> trunc(quantity)) THEN
                    RAISE EXCEPTION '{table}.quantity에 소수점 값이 있어 bigint로 되돌릴 수 없습니다.';
                END IF;
            END
            $$
            """
        ))
        op.alter_column(
            table,
            "quantity",
            existing_type=sa.Numeric(20, 8),
            type_=sa.BigInteger(),
            existing_nullable=False,
            postgresql_using="quantity::bigint",
        )
