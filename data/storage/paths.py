"""Deterministic Azure Blob object path conventions."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _segment(value: str) -> str:
    cleaned = _UNSAFE.sub("-", value.strip()).strip("-.")
    if not cleaned:
        raise ValueError("blob path segment must contain a safe character")
    return cleaned.lower()


def build_raw_path(
    *,
    source: str,
    dataset: str,
    operation: str,
    partition_date: date,
    batch_hash: str,
    page_number: int | None = None,
    migration: bool = False,
    monthly_partition: bool = False,
) -> str:
    """Build a partitioned, content-addressed raw JSONL/gzip path.

    API ingestion keeps the existing day partition by default. Historical Raw
    repartitioning can opt into a YYYY/MM partition so a blob never implies a
    day that does not describe every record it contains.
    """

    if len(batch_hash) != 64:
        raise ValueError("batch_hash must be a SHA-256 hex digest")
    suffix = f"page-{page_number:08d}-" if page_number is not None else ""
    origin = "migration/" if migration else ""
    partition = f"year={partition_date:%Y}/month={partition_date:%m}/"
    if not monthly_partition:
        partition += f"day={partition_date:%d}/"
    return (
        f"{origin}{_segment(source)}/{_segment(dataset)}/"
        f"operation={_segment(operation)}/{partition}"
        f"{suffix}{batch_hash}.jsonl.gz"
    )


def build_processed_path(
    dataset: str,
    *,
    partition_date: date,
    file_name: str,
) -> str:
    return (
        f"{_segment(dataset)}/year={partition_date:%Y}/"
        f"month={partition_date:%m}/{_segment(file_name)}"
    )


def build_feature_path(
    dataset: str,
    *,
    version: str,
    split: str,
    file_name: str,
) -> str:
    return (
        f"{_segment(dataset)}/version={_segment(version)}/"
        f"{_segment(split)}/{_segment(file_name)}"
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
