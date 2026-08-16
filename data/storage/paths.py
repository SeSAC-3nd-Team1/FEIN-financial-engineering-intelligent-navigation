"""Canonical Azure Blob object path conventions."""

from __future__ import annotations

import re
from datetime import date


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _segment(value: str) -> str:
    cleaned = _UNSAFE.sub("-", value.strip()).strip("-.")
    if not cleaned:
        raise ValueError("blob path segment must contain a safe character")
    return cleaned.lower()


def _version(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or any(ch not in "0123456789._-" for ch in cleaned):
        raise ValueError("version contains unsafe characters")
    return cleaned


def build_raw_path(
    *,
    source: str,
    dataset: str,
    operation: str,
    partition_date: date,
    batch_hash: str,
) -> str:
    """Build the only supported Raw layout: source/dataset/operation/YYYY/MM/hash."""

    if not re.fullmatch(r"[0-9a-fA-F]{64}", batch_hash):
        raise ValueError("batch_hash must be a SHA-256 hex digest")
    return (
        f"{_segment(source)}/{_segment(dataset)}/operation={_segment(operation)}/"
        f"year={partition_date:%Y}/month={partition_date:%m}/{batch_hash.lower()}.jsonl.gz"
    )


def build_processed_path(
    dataset: str,
    *,
    partition_date: date,
    schema_version: str,
    file_name: str = "part-00000.parquet",
) -> str:
    return (
        f"{_segment(dataset)}/schema=v{_version(schema_version)}/"
        f"year={partition_date:%Y}/month={partition_date:%m}/{_segment(file_name)}"
    )


def build_feature_path(
    dataset: str,
    *,
    partition_date: date,
    version: str,
    file_name: str = "part-00000.parquet",
) -> str:
    return (
        f"{_segment(dataset)}/version=v{_version(version)}/"
        f"year={partition_date:%Y}/month={partition_date:%m}/{_segment(file_name)}"
    )
