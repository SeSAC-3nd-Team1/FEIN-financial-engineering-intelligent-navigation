"""공공 API 원문을 손실 없이 결정론적 JSONL + gzip 형식으로 저장한다."""

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
    """JSON 기본 인코더가 처리하지 못하는 날짜 타입만 ISO 문자열로 변환한다."""

    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """키 순서와 공백 차이를 제거한 canonical JSON bytes를 만든다.

    같은 payload가 수집 시점이나 dict 입력 순서와 무관하게 같은 hash를 갖도록 하는 것이
    목적이다. 이 표현은 Raw 중복 판정과 재처리 검증의 기준이 된다.
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def payload_hash(payload: dict[str, Any]) -> str:
    """API payload 하나의 canonical SHA-256을 계산한다."""

    return hashlib.sha256(canonical_json(payload)).hexdigest()


@dataclass(frozen=True)
class RawBatch:
    """직렬화된 Raw batch와 무결성/경로 계산에 필요한 hash를 묶는다."""

    data: bytes
    content_sha256: str
    batch_hash: str
    record_count: int


def serialize_jsonl_gzip(records: Iterable[dict[str, Any]]) -> RawBatch:
    """레코드를 재현 가능한 gzip JSONL로 직렬화한다.

    gzip header의 ``mtime``을 0으로 고정해 같은 입력이 항상 같은 압축 bytes를 만들게 한다.
    ``batch_hash``는 record의 ``payloadHash`` 순서에만 의존하므로 content-addressed Raw
    파일명의 안정적인 기준으로 사용할 수 있다.
    """

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
    """canonical monthly Raw object를 content-addressed 방식으로 기록한다."""

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
        """현재 Azure 인증/환경변수 설정으로 writer를 생성한다."""

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
        """API items를 원문 그대로 감싸 월별 Raw Blob에 저장한다.

        payload 자체는 수정하지 않고 수집 메타데이터와 hash만 외부 envelope에 추가한다.
        같은 payload batch를 다시 실행하면 동일한 ``batch_hash`` 경로를 계산하므로 기존
        Blob을 재사용하고 중복 object를 만들지 않는다.
        """

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

        # content-addressed 경로가 이미 존재하면 업로드하지 않는다. 기존 metadata를 읽어
        # 호출자가 신규/재사용 여부와 record count를 같은 방식으로 처리할 수 있게 한다.
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
