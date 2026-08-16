"""데이터 파이프라인에서 공통으로 사용하는 Azure Blob Storage 어댑터다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Mapping

from azure.core.exceptions import ResourceExistsError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings


@dataclass(frozen=True)
class BlobObject:
    """업로드/조회한 Blob object의 최소 메타데이터를 표현한다."""

    container: str
    path: str
    size: int
    etag: str | None
    metadata: dict[str, str]
    created: bool


class BlobStorage:
    """Entra ID 인증을 우선하고 로컬 Azurite만 connection string을 허용한다."""

    def __init__(self, service_client: BlobServiceClient) -> None:
        self.service_client = service_client

    @classmethod
    def from_env(cls) -> "BlobStorage":
        """환경변수에서 안전한 Blob 인증 방식을 선택한다.

        실제 Azure 계정은 ``DefaultAzureCredential``만 사용한다. 개발자의 오래된
        Shared Key connection string이 환경파일에 남아 있어도 account name이 있으면
        identity 인증을 먼저 선택해 운영 보안 정책을 우회하지 못하게 한다.
        """

        account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "").strip()
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()

        # 실제 Azure는 Entra ID / DefaultAzureCredential만 사용한다.
        # 이 분기를 먼저 두어 로컬 환경파일의 오래된 Shared Key가 우선되는 것을 막는다.
        if account_name:
            return cls(
                BlobServiceClient(
                    account_url=f"https://{account_name}.blob.core.windows.net",
                    credential=DefaultAzureCredential(),
                    retry_total=5,
                    retry_backoff_factor=0.8,
                    retry_backoff_max=30,
                )
            )

        # connection string은 로컬 에뮬레이터인 Azurite에만 허용한다.
        # 실제 Azure Account Key/SAS/connection string은 의도적으로 지원하지 않는다.
        if connection_string:
            if connection_string.lower() != "usedevelopmentstorage=true":
                raise RuntimeError(
                    "Azure Shared Key/connection-string authentication is disabled; "
                    "set AZURE_STORAGE_ACCOUNT_NAME and authenticate with Entra ID"
                )
            return cls(BlobServiceClient.from_connection_string(connection_string))

        raise RuntimeError("AZURE_STORAGE_ACCOUNT_NAME is required")

    def exists(self, container: str, path: str) -> bool:
        """지정한 Blob object가 이미 존재하는지 확인한다."""

        return self.service_client.get_blob_client(container, path).exists()

    def properties(self, container: str, path: str) -> BlobObject:
        """기존 Blob의 속성과 사용자 metadata를 읽는다."""

        client = self.service_client.get_blob_client(container, path)
        props = client.get_blob_properties()
        return BlobObject(
            container=container,
            path=path,
            size=props.size,
            etag=props.etag,
            metadata=dict(props.metadata or {}),
            created=False,
        )

    def list_paths(self, container: str, *, prefix: str = "") -> list[str]:
        """prefix 아래의 Blob 경로만 반환한다."""

        client = self.service_client.get_container_client(container)
        return [blob.name for blob in client.list_blobs(name_starts_with=prefix)]

    def download_bytes(self, container: str, path: str) -> bytes:
        """Blob 하나를 bytes로 다운로드한다."""

        client = self.service_client.get_blob_client(container, path)
        return client.download_blob(max_concurrency=4).readall()

    def upload_bytes(
        self,
        container: str,
        path: str,
        data: bytes,
        *,
        metadata: Mapping[str, str] | None = None,
        content_type: str = "application/octet-stream",
        content_encoding: str | None = None,
        overwrite: bool = False,
    ) -> BlobObject:
        """bytes를 업로드하고 이미 존재하면 기존 object 정보를 반환한다.

        content-addressed Raw 경로에서는 같은 데이터가 같은 경로를 사용하므로
        ``ResourceExistsError``를 실패가 아니라 멱등 재실행으로 처리한다.
        """

        client = self.service_client.get_blob_client(container, path)
        try:
            result = client.upload_blob(
                data,
                overwrite=overwrite,
                metadata=dict(metadata or {}),
                content_settings=ContentSettings(
                    content_type=content_type,
                    content_encoding=content_encoding,
                ),
                max_concurrency=4,
            )
        except ResourceExistsError:
            return self.properties(container, path)
        return BlobObject(
            container=container,
            path=path,
            size=len(data),
            etag=getattr(result, "etag", None),
            metadata=dict(metadata or {}),
            created=True,
        )

    def upload_file(
        self,
        container: str,
        path: str,
        source: str | Path | BinaryIO,
        *,
        metadata: Mapping[str, str] | None = None,
        content_type: str = "application/octet-stream",
        overwrite: bool = False,
    ) -> BlobObject:
        """파일 경로나 열린 binary stream을 Blob에 업로드한다.

        함수 내부에서 직접 연 파일만 닫고, 호출자가 넘긴 stream의 lifecycle은 호출자에게
        남겨 둔다.
        """

        close_source = False
        stream: BinaryIO
        if isinstance(source, (str, Path)):
            stream = Path(source).open("rb")
            close_source = True
        else:
            stream = source
        try:
            client = self.service_client.get_blob_client(container, path)
            try:
                result = client.upload_blob(
                    stream,
                    overwrite=overwrite,
                    metadata=dict(metadata or {}),
                    content_settings=ContentSettings(content_type=content_type),
                    max_concurrency=4,
                )
            except ResourceExistsError:
                return self.properties(container, path)
            props = client.get_blob_properties()
            return BlobObject(
                container=container,
                path=path,
                size=props.size,
                etag=getattr(result, "etag", None),
                metadata=dict(metadata or {}),
                created=True,
            )
        finally:
            if close_source:
                stream.close()
