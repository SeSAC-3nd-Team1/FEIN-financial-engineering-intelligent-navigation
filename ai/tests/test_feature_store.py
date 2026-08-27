from datetime import datetime, timezone
from types import SimpleNamespace

from azure.core import MatchConditions
import pandas as pd
import pytest

from data_access.feature_store import FeatureStore, FeatureStoreConfig


class FakeDownload:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def readall(self) -> bytes:
        return self.payload


class FakeBlobClient:
    def __init__(self, payload: bytes, download_options: list[dict]) -> None:
        self.payload = payload
        self.download_options = download_options

    def download_blob(self, **kwargs) -> FakeDownload:
        self.download_options.append(kwargs)
        return FakeDownload(self.payload)


class FakeContainerClient:
    def list_blobs(self, *, name_starts_with: str):
        metadata = {
            "size": 100,
            "etag": "etag-1",
            "last_modified": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        return [
            SimpleNamespace(
                name=f"{name_starts_with}year=2024/month=02/part.parquet",
                **metadata,
            ),
            SimpleNamespace(name=f"{name_starts_with}manifest.json"),
            SimpleNamespace(
                name=f"{name_starts_with}year=2024/month=01/part.parquet",
                **metadata,
            ),
        ]


class FakeServiceClient:
    def __init__(self, payload: bytes = b"") -> None:
        self.payload = payload
        self.download_options: list[dict] = []

    def get_container_client(self, _container: str) -> FakeContainerClient:
        return FakeContainerClient()

    def get_blob_client(self, _container: str, _path: str) -> FakeBlobClient:
        return FakeBlobClient(self.payload, self.download_options)


def test_dataset_prefix_normalizes_version_and_rejects_paths() -> None:
    assert FeatureStore.dataset_prefix("model_stock_daily", "v2") == "model_stock_daily/version=v2/"
    assert FeatureStore.dataset_prefix("algorithm_ohlcv", "2") == "algorithm_ohlcv/version=v2/"
    with pytest.raises(ValueError):
        FeatureStore.dataset_prefix("../raw", "2")
    with pytest.raises(ValueError, match="safe version"):
        FeatureStore.dataset_prefix("model_stock_daily", "..")


def test_parquet_paths_are_filtered_and_sorted() -> None:
    store = FeatureStore(FeatureStoreConfig("account"), client=FakeServiceClient())
    assert store.parquet_paths("model_stock_daily", "2") == (
        "model_stock_daily/version=v2/year=2024/month=01/part.parquet",
        "model_stock_daily/version=v2/year=2024/month=02/part.parquet",
    )
    first = store.parquet_files("model_stock_daily", "2")[0]
    assert first.size == 100
    assert first.etag == "etag-1"
    assert first.last_modified == "2026-01-01T00:00:00+00:00"


def test_parquet_listing_rejects_unapproved_dataset() -> None:
    store = FeatureStore(FeatureStoreConfig("account"), client=FakeServiceClient())

    with pytest.raises(ValueError, match="approved"):
        store.parquet_paths("financial_snapshot", "2")


def test_read_partition_supports_column_projection() -> None:
    source = pd.DataFrame({"stock_code": ["005930"], "close_price": [70000]})
    payload = source.to_parquet(index=False)
    client = FakeServiceClient(payload)
    store = FeatureStore(FeatureStoreConfig("account"), client=client)
    actual = store.read_partition(
        "model_stock_daily/version=v2/year=2024/month=01/part.parquet",
        columns=["stock_code"],
        etag="etag-1",
    )
    pd.testing.assert_frame_equal(actual, source[["stock_code"]])
    assert client.download_options == [
        {"etag": "etag-1", "match_condition": MatchConditions.IfNotModified}
    ]


@pytest.mark.parametrize(
    "path",
    [
        "../raw/secrets.parquet",
        "model_stock_daily/year=2024/part.parquet",
        "model_stock_daily/version=/part.parquet",
        "model_stock_daily/version=v../part.parquet",
        "model_stock_daily/version=v2/manifest.json",
    ],
)
def test_read_partition_rejects_unapproved_or_unversioned_paths(path: str) -> None:
    store = FeatureStore(FeatureStoreConfig("account"), client=FakeServiceClient())
    with pytest.raises(ValueError):
        store.read_partition(path)


def test_training_manifest_rejects_non_stock_dataset() -> None:
    store = FeatureStore(FeatureStoreConfig("account"), client=FakeServiceClient())

    with pytest.raises(ValueError, match="model_stock_daily only"):
        store.build_training_manifest("market_index_daily", "2")
