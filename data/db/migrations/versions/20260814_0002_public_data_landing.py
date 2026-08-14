"""add public data API landing table

Revision ID: 20260814_0002
Revises: 20260813_0001
Create Date: 2026-08-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260814_0002"
down_revision: str | None = "20260813_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "public_data_record",
        sa.Column("record_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("dataset", sa.String(length=50), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("reference_date", sa.Date()),
        sa.Column("stock_code", sa.String(length=20)),
        sa.Column("isin", sa.String(length=20)),
        sa.Column("corporation_registration_number", sa.String(length=20)),
        sa.Column("corporation_name", sa.String(length=200)),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("record_id", name="pk_public_data_record"),
        sa.UniqueConstraint(
            "dataset",
            "operation",
            "payload_hash",
            name="uq_public_data_record_dataset_operation_hash",
        ),
        schema="raw",
    )
    op.create_index(
        "ix_public_data_record_dataset_operation_date",
        "public_data_record",
        ["dataset", "operation", "reference_date"],
        schema="raw",
    )
    op.create_index(
        "ix_public_data_record_stock_date",
        "public_data_record",
        ["stock_code", "reference_date"],
        schema="raw",
    )
    op.create_index(
        "ix_public_data_record_corporation_date",
        "public_data_record",
        ["corporation_registration_number", "reference_date"],
        schema="raw",
    )


def downgrade() -> None:
    op.drop_table("public_data_record", schema="raw")
