"""Lossless landing storage for heterogeneous public-data API responses."""

from datetime import date

from sqlalchemy import (
    BigInteger,
    Date,
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
