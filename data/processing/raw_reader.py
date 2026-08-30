"""Canonical Raw JSONL.GZ를 Blob 단위로 읽고 API payload와 lineage를 분리한다."""
from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass
from typing import Any, Iterator

RAW_RE = re.compile(
    r"^data-go-kr/(?P<dataset>[^/]+)/operation=(?P<operation>[^/]+)/"
    r"year=(?P<year>\d{4})/month=(?P<month>\d{2})/(?P<hash>[0-9a-f]{64})\.jsonl\.gz$"
)

@dataclass(frozen=True)
class RawBlob:
    path: str
    dataset: str
    operation: str
    year: int
    month: int
    size: int

@dataclass(frozen=True)
class RawRecord:
    payload: dict[str, Any]
    source: str
    dataset: str
    operation: str
    payload_hash: str | None
    collected_at: str | None
    legacy_present: bool
    source_blob: str


def list_raw_blobs(storage, container: str, dataset: str, operation: str | None = None) -> list[RawBlob]:
    prefix = f"data-go-kr/{dataset}/"
    if operation:
        prefix += f"operation={operation.lower()}/"
    client = storage.service_client.get_container_client(container)
    result: list[RawBlob] = []
    for blob in client.list_blobs(name_starts_with=prefix):
        match = RAW_RE.fullmatch(str(blob.name))
        if not match:
            continue
        result.append(RawBlob(
            path=str(blob.name), dataset=match.group("dataset"), operation=match.group("operation"),
            year=int(match.group("year")), month=int(match.group("month")), size=int(blob.size or 0),
        ))
    return sorted(result, key=lambda item: (item.dataset, item.operation, item.year, item.month, item.path))


def read_blob_records(storage, container: str, blob: RawBlob) -> Iterator[RawRecord]:
    raw = storage.download_bytes(container, blob.path)
    for line_number, raw_line in enumerate(gzip.decompress(raw).splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Raw JSONL line is not object: {blob.path}:{line_number}")
        payload = value.get("payload")
        if not isinstance(payload, dict):
            raise ValueError(f"Raw envelope payload is not object: {blob.path}:{line_number}")
        if str(value.get("dataset", "")) != blob.dataset:
            raise ValueError(f"Raw envelope dataset mismatch: {blob.path}:{line_number}")
        yield RawRecord(
            payload=payload, source=str(value.get("source", "")), dataset=blob.dataset,
            operation=blob.operation, payload_hash=str(value["payloadHash"]) if value.get("payloadHash") else None,
            collected_at=str(value["collectedAt"]) if value.get("collectedAt") else None,
            legacy_present=value.get("legacy") is not None, source_blob=blob.path,
        )
