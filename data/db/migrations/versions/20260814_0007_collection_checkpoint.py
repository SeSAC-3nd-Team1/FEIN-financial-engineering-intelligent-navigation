"""add resumable public-data collection checkpoints

Revision ID: 20260814_0007
Revises: 20260814_0006
Create Date: 2026-08-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from db.models.stock import RAW_SCHEMA


revision: str = "20260814_0007"
down_revision: str | None = "20260814_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "public_data_collection_checkpoint",
        sa.Column("checkpoint_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("dataset", sa.String(length=50), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("range_start", sa.Date(), nullable=False),
        sa.Column("range_end", sa.Date(), nullable=False),
        sa.Column("rows_per_page", sa.Integer(), nullable=False),
        sa.Column("next_page", sa.Integer(), server_default="1", nullable=False),
        sa.Column("total_count", sa.BigInteger(), nullable=True),
        sa.Column("received_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("checkpoint_id"),
        sa.UniqueConstraint(
            "dataset",
            "operation",
            "range_start",
            "range_end",
            name="uq_public_data_checkpoint_operation_range",
        ),
        schema=RAW_SCHEMA,
    )
    op.create_index(
        "ix_public_data_checkpoint_status",
        "public_data_collection_checkpoint",
        ["status", "updated_at"],
        schema=RAW_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_public_data_checkpoint_status",
        table_name="public_data_collection_checkpoint",
        schema=RAW_SCHEMA,
    )
    op.drop_table("public_data_collection_checkpoint", schema=RAW_SCHEMA)
