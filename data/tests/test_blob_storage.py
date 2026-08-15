import gzip
import io
import json
from datetime import date, datetime, timezone

from storage.blob import BlobObject
from storage.paths import build_feature_path, build_processed_path, build_raw_path
from storage.raw import RawBlobWriter, payload_hash, serialize_jsonl_gzip


class FakeBlobStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], BlobObject] = {}
        self.upload_count = 0

    def exists(self, container: str, path: str) -> bool:
        return (container, path) in self.objects

    def properties(self, container: str, path: str) -> BlobObject:
        item = self.objects[(container, path)]
        return BlobObject(
            item.container, item.path, item.size, item.etag, item.metadata, False
        )

    def upload_bytes(self, container, path, data, *, metadata, **kwargs):
        self.upload_count += 1
        result = BlobObject(container, path, len(data), "etag", dict(metadata), True)
        self.objects[(container, path)] = result
        return result


def test_raw_path_is_partitioned_and_content_addressed() -> None:
    path = build_raw_path(
        source="data-go-kr",
        dataset="stock_price",
        operation="getStockPriceInfo",
        partition_date=date(2026, 8, 15),
        page_number=12,
        batch_hash="a" * 64,
    )
    assert path == (
        "data-go-kr/stock_price/operation=getstockpriceinfo/"
        "year=2026/month=08/day=15/page-00000012-" + "a" * 64 + ".jsonl.gz"
    )


def test_processed_and_feature_paths_capture_reproducibility_dimensions() -> None:
    assert build_processed_path(
        "stock_price", partition_date=date(2026, 8, 15), file_name="part-1.parquet"
    ) == "stock_price/year=2026/month=08/part-1.parquet"
    assert build_feature_path(
        "stock_prediction", version="v1", split="train", file_name="part.parquet"
    ) == "stock_prediction/version=v1/train/part.parquet"


def test_jsonl_gzip_is_lossless_and_deterministic() -> None:
    payload = {"name": "삼성전자", "price": 80700}
    record = {
        "dataset": "stock_price",
        "operation": "getStockPriceInfo",
        "source": "data-go-kr",
        "collectedAt": datetime(2026, 8, 15, tzinfo=timezone.utc),
        "payloadHash": payload_hash(payload),
        "payload": payload,
    }
    first = serialize_jsonl_gzip([record])
    second = serialize_jsonl_gzip([record])
    assert first.data == second.data
    decoded = [
        json.loads(line)
        for line in gzip.GzipFile(fileobj=io.BytesIO(first.data), mode="rb")
    ]
    assert decoded[0]["payload"] == payload
    assert decoded[0]["payloadHash"] == payload_hash(payload)
    assert first.content_sha256 == second.content_sha256


def test_raw_writer_reuses_existing_content_addressed_blob() -> None:
    storage = FakeBlobStorage()
    writer = RawBlobWriter(storage, container="raw")
    kwargs = {
        "dataset": "stock_price",
        "operation": "getStockPriceInfo",
        "items": [{"basDt": "20260815", "srtnCd": "005930"}],
        "partition_date": date(2026, 8, 15),
        "page_number": 1,
        "collected_at": datetime(2026, 8, 15, tzinfo=timezone.utc),
    }
    first, first_batch = writer.upload_items(**kwargs)
    second, second_batch = writer.upload_items(**kwargs)
    assert first.path == second.path
    assert first_batch.batch_hash == second_batch.batch_hash
    assert storage.upload_count == 1
    assert second.created is False
