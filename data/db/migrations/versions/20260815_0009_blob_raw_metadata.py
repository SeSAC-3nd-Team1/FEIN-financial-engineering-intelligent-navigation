"""add blob raw object metadata and migration manifest

Revision ID: 20260815_0009
Revises: 20260815_0008
Create Date: 2026-08-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260815_0009"
down_revision: str | None = "20260815_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_object",
        sa.Column("data_object_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("dataset", sa.String(length=50), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("container", sa.String(length=63), nullable=False),
        sa.Column("blob_path", sa.String(length=1024), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("batch_hash", sa.String(length=64), nullable=False),
        sa.Column("record_count", sa.BigInteger(), nullable=False),
        sa.Column("range_start", sa.Date()),
        sa.Column("range_end", sa.Date()),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "compression", sa.String(length=20), server_default="gzip", nullable=False
        ),
        sa.Column(
            "status", sa.String(length=20), server_default="available", nullable=False
        ),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("data_object_id", name="pk_data_object"),
        sa.UniqueConstraint("container", "blob_path", name="uq_data_object_blob"),
        schema="raw",
    )
    op.create_index(
        "ix_data_object_dataset_operation_collected",
        "data_object",
        ["dataset", "operation", "collected_at"],
        schema="raw",
    )
    op.create_index(
        "ix_data_object_status_updated",
        "data_object",
        ["status", "updated_at"],
        schema="raw",
    )

    op.create_table(
        "public_data_migration_manifest",
        sa.Column("manifest_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_table", sa.String(length=100), nullable=False),
        sa.Column("dataset", sa.String(length=50), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("source_min_id", sa.BigInteger(), nullable=False),
        sa.Column("source_max_id", sa.BigInteger(), nullable=False),
        sa.Column("migrated_row_count", sa.BigInteger(), nullable=False),
        sa.Column("container", sa.String(length=63), nullable=False),
        sa.Column("blob_path", sa.String(length=1024), nullable=False),
        sa.Column("blob_size", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="complete", nullable=False
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
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
        sa.PrimaryKeyConstraint(
            "manifest_id", name="pk_public_data_migration_manifest"
        ),
        sa.UniqueConstraint(
            "source_table", "dataset", "operation", "source_min_id", "source_max_id",
            name="uq_public_data_migration_source_chunk",
        ),
        schema="raw",
    )
    op.create_index(
        "ix_public_data_migration_status",
        "public_data_migration_manifest",
        ["status", "dataset", "operation"],
        schema="raw",
    )


def downgrade() -> None:
    op.drop_table("public_data_migration_manifest", schema="raw")
    op.drop_table("data_object", schema="raw")
