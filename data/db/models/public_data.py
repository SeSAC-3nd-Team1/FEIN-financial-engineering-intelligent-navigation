"""Lossless landing storage for heterogeneous public-data API responses."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models.common import TimestampMixin
from db.models.stock import RAW_SCHEMA


class PublicDataRecord(TimestampMixin, Base):
    """One exact item returned by a data.go.kr operation.

    Exact duplicates are coalesced by ``payload_hash``. A corrected response produces
    a new row, preserving the values that were observed previously.
    """

    __tablename__ = "public_data_record"
    __table_args__ = (
        UniqueConstraint(
            "dataset",
            "operation",
            "payload_hash",
            name="uq_public_data_record_dataset_operation_hash",
        ),
        Index(
            "ix_public_data_record_dataset_operation_date",
            "dataset",
            "operation",
            "reference_date",
        ),
        Index(
            "ix_public_data_record_stock_date", "stock_code", "reference_date"
        ),
        Index(
            "ix_public_data_record_corporation_date",
            "corporation_registration_number",
            "reference_date",
        ),
        {"schema": RAW_SCHEMA},
    )

    record_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    dataset: Mapped[str] = mapped_column(String(50), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_date: Mapped[date | None] = mapped_column(Date)
    stock_code: Mapped[str | None] = mapped_column(String(20))
    isin: Mapped[str | None] = mapped_column(String(20))
    corporation_registration_number: Mapped[str | None] = mapped_column(String(20))
    corporation_name: Mapped[str | None] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class PublicDataCollectionCheckpoint(TimestampMixin, Base):
    """Resume marker for bounded date-range backfills."""

    __tablename__ = "public_data_collection_checkpoint"
    __table_args__ = (
        UniqueConstraint(
            "dataset",
            "operation",
            "range_start",
            "range_end",
            name="uq_public_data_checkpoint_operation_range",
        ),
        Index("ix_public_data_checkpoint_status", "status", "updated_at"),
        {"schema": RAW_SCHEMA},
    )

    checkpoint_id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    dataset: Mapped[str] = mapped_column(String(50), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    range_start: Mapped[date] = mapped_column(Date, nullable=False)
    range_end: Mapped[date] = mapped_column(Date, nullable=False)
    rows_per_page: Mapped[int] = mapped_column(Integer, nullable=False)
    next_page: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    total_count: Mapped[int | None] = mapped_column(BigInteger)
    received_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    last_error: Mapped[str | None] = mapped_column(Text)


class RawDataObject(TimestampMixin, Base):
    """Searchable metadata for an immutable raw object stored outside PostgreSQL."""

    __tablename__ = "data_object"
    __table_args__ = (
        UniqueConstraint("container", "blob_path", name="uq_data_object_blob"),
        Index(
            "ix_data_object_dataset_operation_collected",
            "dataset",
            "operation",
            "collected_at",
        ),
        Index("ix_data_object_status_updated", "status", "updated_at"),
        {"schema": RAW_SCHEMA},
    )

    data_object_id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    dataset: Mapped[str] = mapped_column(String(50), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    container: Mapped[str] = mapped_column(String(63), nullable=False)
    blob_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    range_start: Mapped[date | None] = mapped_column(Date)
    range_end: Mapped[date | None] = mapped_column(Date)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    compression: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'gzip'")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'available'")
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class RawMigrationManifest(TimestampMixin, Base):
    """Resumable chunk ledger for legacy public_data_record migration."""

    __tablename__ = "public_data_migration_manifest"
    __table_args__ = (
        UniqueConstraint(
            "source_table",
            "dataset",
            "operation",
            "source_min_id",
            "source_max_id",
            name="uq_public_data_migration_source_chunk",
        ),
        Index(
            "ix_public_data_migration_status",
            "status",
            "dataset",
            "operation",
        ),
        {"schema": RAW_SCHEMA},
    )

    manifest_id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    source_table: Mapped[str] = mapped_column(String(100), nullable=False)
    dataset: Mapped[str] = mapped_column(String(50), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    source_min_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_max_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    migrated_row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    container: Mapped[str] = mapped_column(String(63), nullable=False)
    blob_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    blob_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'complete'")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
