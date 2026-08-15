"""Small Azure Blob SDK adapter shared by data pipelines."""

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
    container: str
    path: str
    size: int
    etag: str | None
    metadata: dict[str, str]
    created: bool


class BlobStorage:
    """Identity-first Blob access with optional Azurite connection-string support."""

    def __init__(self, service_client: BlobServiceClient) -> None:
        self.service_client = service_client

    @classmethod
    def from_env(cls) -> "BlobStorage":
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
        if connection_string:
            return cls(BlobServiceClient.from_connection_string(connection_string))
        account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "").strip()
        if not account_name:
            raise RuntimeError("AZURE_STORAGE_ACCOUNT_NAME is required")
        return cls(
            BlobServiceClient(
                account_url=f"https://{account_name}.blob.core.windows.net",
                credential=DefaultAzureCredential(),
                retry_total=5,
                retry_backoff_factor=0.8,
                retry_backoff_max=30,
            )
        )

    def exists(self, container: str, path: str) -> bool:
        return self.service_client.get_blob_client(container, path).exists()

    def properties(self, container: str, path: str) -> BlobObject:
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
