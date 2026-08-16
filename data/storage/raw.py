"""Lossless, deterministic JSON Lines + gzip storage for public API records."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable

from storage.blob import BlobObject, BlobStorage
from storage.paths import build_raw_path


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


@dataclass(frozen=True)
class RawBatch:
    data: bytes
    content_sha256: str
    batch_hash: str
    record_count: int


def serialize_jsonl_gzip(records: Iterable[dict[str, Any]]) -> RawBatch:
    rows = list(records)
    batch_digest = hashlib.sha256()
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as compressed:
        for row in rows:
            encoded = canonical_json(row)
            compressed.write(encoded)
            compressed.write(b"\n")
            batch_digest.update(str(row.get("payloadHash", "")).encode("ascii"))
            batch_digest.update(b"\n")
    data = output.getvalue()
    return RawBatch(
        data=data,
        content_sha256=hashlib.sha256(data).hexdigest(),
        batch_hash=batch_digest.hexdigest(),
        record_count=len(rows),
    )


class RawBlobWriter:
    def __init__(
        self,
        storage: BlobStorage,
        *,
        container: str | None = None,
        source: str = "data-go-kr",
    ) -> None:
        self.storage = storage
        self.container = container or os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
        self.source = source

    @classmethod
    def from_env(cls) -> "RawBlobWriter":
        return cls(BlobStorage.from_env())

    def upload_items(
        self,
        *,
        dataset: str,
        operation: str,
        items: list[dict[str, Any]],
        partition_date: date,
        collected_at: datetime | None = None,
    ) -> tuple[BlobObject, RawBatch]:
        observed_at = collected_at or datetime.now(timezone.utc)
        records = [
            {
                "dataset": dataset,
                "operation": operation,
                "source": self.source,
                "collectedAt": observed_at,
                "payloadHash": payload_hash(item),
                "payload": item,
            }
            for item in items
        ]
        batch = serialize_jsonl_gzip(records)
        path = build_raw_path(
            source=self.source,
            dataset=dataset,
            operation=operation,
            partition_date=partition_date,
            batch_hash=batch.batch_hash,
        )
        if self.storage.exists(self.container, path):
            existing = self.storage.properties(self.container, path)
            return existing, RawBatch(
                data=b"",
                content_sha256=existing.metadata.get("content_sha256", batch.content_sha256),
                batch_hash=batch.batch_hash,
                record_count=int(existing.metadata.get("record_count", batch.record_count)),
            )
        blob = self.storage.upload_bytes(
            self.container,
            path,
            batch.data,
            metadata={
                "content_sha256": batch.content_sha256,
                "batch_hash": batch.batch_hash,
                "record_count": str(batch.record_count),
                "format": "jsonl-gzip",
                "dataset": dataset,
                "operation": operation,
                "source": self.source,
            },
            content_type="application/gzip",
        )
        return blob, batch
