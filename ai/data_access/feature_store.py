"""Read-only Azure Blob access for versioned Parquet feature datasets."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import PurePosixPath
from typing import Iterable

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
import pandas as pd


@dataclass(frozen=True)
class FeatureStoreConfig:
    """Feature store connection settings loaded without embedding credentials."""

    account_name: str
    container: str = "features"

    @classmethod
    def from_env(cls) -> "FeatureStoreConfig":
        account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "").strip()
        if not account_name:
            raise RuntimeError("AZURE_STORAGE_ACCOUNT_NAME is required")
        return cls(
            account_name=account_name,
            container=os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features").strip() or "features",
        )


class FeatureStore:
    """Load immutable feature partitions through Entra ID authentication."""

    def __init__(self, config: FeatureStoreConfig, client: BlobServiceClient | None = None) -> None:
        self.config = config
        self.client = client or BlobServiceClient(
            account_url=f"https://{config.account_name}.blob.core.windows.net",
            credential=DefaultAzureCredential(),
            retry_total=5,
            retry_backoff_factor=0.8,
            retry_backoff_max=30,
        )

    @staticmethod
    def dataset_prefix(dataset: str, version: str) -> str:
        if not dataset or PurePosixPath(dataset).name != dataset:
            raise ValueError("dataset must be a single safe path segment")
        normalized_version = version.removeprefix("v")
        if not normalized_version or PurePosixPath(normalized_version).name != normalized_version:
            raise ValueError("version must be a single safe path segment")
        return f"{dataset}/version=v{normalized_version}/"

    def parquet_paths(self, dataset: str, version: str) -> tuple[str, ...]:
        prefix = self.dataset_prefix(dataset, version)
        container = self.client.get_container_client(self.config.container)
        return tuple(
            sorted(
                blob.name
                for blob in container.list_blobs(name_starts_with=prefix)
                if blob.name.endswith(".parquet")
            )
        )

    def read_partition(self, path: str, columns: Iterable[str] | None = None) -> pd.DataFrame:
        expected_prefixes = ("model_stock_daily/", "market_index_daily/", "macro_daily/")
        if path.startswith("/") or ".." in PurePosixPath(path).parts or not path.startswith(expected_prefixes):
            raise ValueError("path is outside an approved feature dataset")
        payload = self.client.get_blob_client(self.config.container, path).download_blob().readall()
        return pd.read_parquet(BytesIO(payload), columns=list(columns) if columns is not None else None)
