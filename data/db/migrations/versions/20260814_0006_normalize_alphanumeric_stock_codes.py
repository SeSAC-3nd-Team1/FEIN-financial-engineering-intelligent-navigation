"""normalize A-prefixed alphanumeric KRX stock codes

Revision ID: 20260814_0006
Revises: 20260814_0005
Create Date: 2026-08-14
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260814_0006"
down_revision: str | None = "20260814_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Numeric prefixed codes were handled by 0004. This catches newer KRX
    # alphanumeric short codes such as A0001A0 -> 0001A0.
    op.execute(
        """
        UPDATE raw.stock_master
        SET stock_code = substring(stock_code FROM 2)
        WHERE stock_code ~ '^A[A-Z0-9]{6}$'
        """
    )
    op.execute(
        """
        UPDATE raw.public_data_record
        SET stock_code = substring(stock_code FROM 2)
        WHERE stock_code ~ '^A[A-Z0-9]{6}$'
        """
    )


def downgrade() -> None:
    pass
