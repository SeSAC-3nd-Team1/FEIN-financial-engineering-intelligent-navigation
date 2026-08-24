"""OpenDART 원문을 일자 partition에 변경 없이 보존한다."""

from __future__ import annotations

from datetime import date
import hashlib
import json
import os
from typing import Any

from storage.blob import BlobObject, BlobStorage


class OpenDartRawWriter:
    """원문 hash 기반 경로로 OpenDART 응답을 멱등 저장한다."""

    def __init__(self, storage: BlobStorage, *, container: str | None = None) -> None:
        self.storage = storage
        self.container = container or os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")

    @classmethod
    def from_env(cls) -> "OpenDartRawWriter":
        """프로젝트 공통 Azure 인증으로 writer를 만든다."""

        return cls(BlobStorage.from_env())

    def upload_bytes(
        self,
        *,
        dataset: str,
        content: bytes,
        partition_date: date,
        stock_code: str | None = None,
        extension: str,
        content_type: str,
    ) -> BlobObject:
        """API 원문 bytes를 수정하지 않고 content-addressed object로 저장한다."""

        digest = hashlib.sha256(content).hexdigest()
        prefix = f"opendart/{dataset}"
        if stock_code:
            prefix += f"/{stock_code}"
        path = f"{prefix}/{partition_date:%Y/%m/%d}/{digest}.{extension.lstrip('.')}"
        return self.storage.upload_bytes(
            self.container,
            path,
            content,
            metadata={"source": "opendart", "dataset": dataset, "content_sha256": digest},
            content_type=content_type,
        )

    def upload_json(
        self,
        *,
        dataset: str,
        payload: dict[str, Any],
        partition_date: date,
        stock_code: str | None = None,
    ) -> BlobObject:
        """JSON 응답을 정렬이나 필드 변경 없이 UTF-8 JSON으로 저장한다."""

        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self.upload_bytes(
            dataset=dataset,
            content=content,
            partition_date=partition_date,
            stock_code=stock_code,
            extension="json",
            content_type="application/json",
        )
