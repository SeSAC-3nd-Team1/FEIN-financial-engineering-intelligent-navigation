from types import SimpleNamespace

import pandas as pd
import pytest

from data_access.feature_store import FeatureStore, FeatureStoreConfig


class FakeDownload:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def readall(self) -> bytes:
        return self.payload


class FakeBlobClient:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def download_blob(self) -> FakeDownload:
        return FakeDownload(self.payload)


class FakeContainerClient:
    def list_blobs(self, *, name_starts_with: str):
        return [
            SimpleNamespace(name=f"{name_starts_with}year=2024/month=02/part.parquet"),
            SimpleNamespace(name=f"{name_starts_with}manifest.json"),
            SimpleNamespace(name=f"{name_starts_with}year=2024/month=01/part.parquet"),
        ]


class FakeServiceClient:
    def __init__(self, payload: bytes = b"") -> None:
        self.payload = payload

    def get_container_client(self, _container: str) -> FakeContainerClient:
        return FakeContainerClient()

    def get_blob_client(self, _container: str, _path: str) -> FakeBlobClient:
        return FakeBlobClient(self.payload)


def test_dataset_prefix_normalizes_version_and_rejects_paths() -> None:
    assert FeatureStore.dataset_prefix("model_stock_daily", "v2") == "model_stock_daily/version=v2/"
    with pytest.raises(ValueError):
        FeatureStore.dataset_prefix("../raw", "2")


def test_parquet_paths_are_filtered_and_sorted() -> None:
    store = FeatureStore(FeatureStoreConfig("account"), client=FakeServiceClient())
    assert store.parquet_paths("model_stock_daily", "2") == (
        "model_stock_daily/version=v2/year=2024/month=01/part.parquet",
        "model_stock_daily/version=v2/year=2024/month=02/part.parquet",
    )


def test_read_partition_supports_column_projection() -> None:
    source = pd.DataFrame({"stock_code": ["005930"], "close_price": [70000]})
    payload = source.to_parquet(index=False)
    store = FeatureStore(FeatureStoreConfig("account"), client=FakeServiceClient(payload))
    actual = store.read_partition(
        "model_stock_daily/version=v2/year=2024/month=01/part.parquet",
        columns=["stock_code"],
    )
    pd.testing.assert_frame_equal(actual, source[["stock_code"]])


def test_read_partition_rejects_unapproved_paths() -> None:
    store = FeatureStore(FeatureStoreConfig("account"), client=FakeServiceClient())
    with pytest.raises(ValueError):
        store.read_partition("../raw/secrets.parquet")
