"""normalize Public Data Portal A-prefixed stock codes

Revision ID: 20260814_0004
Revises: 20260814_0003
Create Date: 2026-08-14
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260814_0004"
down_revision: str | None = "20260814_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Merge any rows collected before canonicalization into an already-present
    # six-digit master row. Payload JSON remains untouched as the raw record.
    op.execute(
        """
        DELETE FROM raw.stock_price_daily legacy_price
        USING raw.stock_master legacy, raw.stock_master canonical,
              raw.stock_price_daily canonical_price
        WHERE legacy.stock_code ~ '^A[A-Z0-9]{6}$'
          AND canonical.stock_code = substring(legacy.stock_code FROM 2)
          AND legacy_price.stock_id = legacy.stock_id
          AND canonical_price.stock_id = canonical.stock_id
          AND canonical_price.trade_date = legacy_price.trade_date
          AND canonical_price.price_type = legacy_price.price_type
        """
    )
    op.execute(
        """
        DELETE FROM raw.stock_issuance legacy_issuance
        USING raw.stock_master legacy, raw.stock_master canonical,
              raw.stock_issuance canonical_issuance
        WHERE legacy.stock_code ~ '^A[A-Z0-9]{6}$'
          AND canonical.stock_code = substring(legacy.stock_code FROM 2)
          AND legacy_issuance.stock_id = legacy.stock_id
          AND canonical_issuance.stock_id = canonical.stock_id
          AND canonical_issuance.reference_date = legacy_issuance.reference_date
        """
    )
    for table in ("stock_price_daily", "stock_issuance", "financial_statement"):
        op.execute(
            f"""
            UPDATE raw.{table} child
            SET stock_id = canonical.stock_id
            FROM raw.stock_master legacy, raw.stock_master canonical
            WHERE legacy.stock_code ~ '^A[A-Z0-9]{{6}}$'
              AND canonical.stock_code = substring(legacy.stock_code FROM 2)
              AND child.stock_id = legacy.stock_id
            """
        )
    op.execute(
        """
        DELETE FROM raw.stock_master legacy
        USING raw.stock_master canonical
        WHERE legacy.stock_code ~ '^A[A-Z0-9]{6}$'
          AND canonical.stock_code = substring(legacy.stock_code FROM 2)
        """
    )
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
    # Canonical codes are intentionally not made ambiguous again.
    pass
