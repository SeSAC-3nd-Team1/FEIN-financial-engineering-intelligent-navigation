"""Read-only Azure Blob access for versioned Parquet feature datasets."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import PurePosixPath
import re
from typing import Iterable

from azure.core import MatchConditions
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
import pandas as pd

from data_access.dataset_manifest import (
    DatasetContract,
    FeatureFile,
    TrainingDatasetManifest,
    build_training_manifest,
)


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

    APPROVED_DATASETS = frozenset(
        {"model_stock_daily", "algorithm_ohlcv", "market_index_daily", "macro_daily"}
    )

    def __init__(self, config: FeatureStoreConfig, client: BlobServiceClient | None = None) -> None:
        self.config = config
        self.client = client or BlobServiceClient(
            account_url=f"https://{config.account_name}.blob.core.windows.net",
            credential=DefaultAzureCredential(),
            retry_total=5,
            retry_backoff_factor=0.8,
            retry_backoff_max=30,
        )

    @classmethod
    def dataset_prefix(cls, dataset: str, version: str) -> str:
        if dataset not in cls.APPROVED_DATASETS or PurePosixPath(dataset).name != dataset:
            raise ValueError("dataset must be an approved feature dataset")
        normalized_version = version.removeprefix("v")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", normalized_version):
            raise ValueError("version must be a safe version identifier")
        return f"{dataset}/version=v{normalized_version}/"

    def parquet_files(self, dataset: str, version: str) -> tuple[FeatureFile, ...]:
        prefix = self.dataset_prefix(dataset, version)
        container = self.client.get_container_client(self.config.container)
        files = []
        for blob in container.list_blobs(name_starts_with=prefix):
            if not blob.name.endswith(".parquet"):
                continue
            last_modified = getattr(blob, "last_modified", None)
            files.append(
                FeatureFile(
                    path=blob.name,
                    size=int(getattr(blob, "size", 0)),
                    etag=str(getattr(blob, "etag", "")) or None,
                    last_modified=last_modified.isoformat() if last_modified else None,
                )
            )
        return tuple(sorted(files, key=lambda file: file.path))

    def parquet_paths(self, dataset: str, version: str) -> tuple[str, ...]:
        return tuple(file.path for file in self.parquet_files(dataset, version))

    def read_partition(
        self,
        path: str,
        columns: Iterable[str] | None = None,
        *,
        etag: str | None = None,
    ) -> pd.DataFrame:
        parts = PurePosixPath(path).parts
        versioned_path = (
            len(parts) >= 3
            and parts[0] in self.APPROVED_DATASETS
            and re.fullmatch(r"version=v[A-Za-z0-9][A-Za-z0-9._-]*", parts[1]) is not None
            and path.endswith(".parquet")
        )
        if path.startswith("/") or ".." in parts or not versioned_path:
            raise ValueError("path must be an approved, versioned Parquet feature partition")
        download_options = (
            {"etag": etag, "match_condition": MatchConditions.IfNotModified}
            if etag is not None
            else {}
        )
        payload = (
            self.client.get_blob_client(self.config.container, path)
            .download_blob(**download_options)
            .readall()
        )
        return pd.read_parquet(BytesIO(payload), columns=list(columns) if columns is not None else None)

    def build_training_manifest(
        self,
        dataset: str,
        version: str,
        *,
        contract: DatasetContract = DatasetContract(),
    ) -> TrainingDatasetManifest:
        """Read, validate, and identify one model_stock_daily version."""

        if dataset != "model_stock_daily":
            raise ValueError("training manifest contract supports model_stock_daily only")
        files = self.parquet_files(dataset, version)
        frames = tuple(
            self.read_partition(file.path, etag=file.etag) for file in files
        )
        return build_training_manifest(
            dataset=dataset,
            version=version,
            files=files,
            frames=frames,
            contract=contract,
        )
