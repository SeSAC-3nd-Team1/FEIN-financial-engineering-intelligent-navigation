from datetime import datetime, timezone

import pytest

from scripts.reconcile_raw_blob_catalog import build_catalog_row


def test_build_catalog_row_uses_month_partition_and_blob_metadata() -> None:
    row = build_catalog_row(
        container="raw",
        path=(
            "data-go-kr/stock_price/operation=getstockpriceinfo/"
            "year=2026/month=08/abc.jsonl.gz"
        ),
        size=1234,
        metadata={
            "dataset": "stock_price",
            "operation": "getStockPriceInfo",
            "source": "data-go-kr",
            "content_sha256": "a" * 64,
            "batch_hash": "b" * 64,
            "record_count": "2872",
        },
        created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )

    assert row["dataset"] == "stock_price"
    assert row["operation"] == "getStockPriceInfo"
    assert row["range_start"].isoformat() == "2026-08-01"
    assert row["range_end"].isoformat() == "2026-08-31"
    assert row["record_count"] == 2872
    assert row["file_size"] == 1234
    assert row["status"] == "available"


def test_build_catalog_row_rejects_missing_required_metadata() -> None:
    with pytest.raises(ValueError, match="missing Blob metadata"):
        build_catalog_row(
            container="raw",
            path=(
                "data-go-kr/stock_price/operation=getstockpriceinfo/"
                "year=2026/month=08/abc.jsonl.gz"
            ),
            size=1,
            metadata={"dataset": "stock_price", "operation": "getStockPriceInfo"},
            created_at=None,
        )


def test_build_catalog_row_rejects_legacy_day_partition() -> None:
    with pytest.raises(ValueError, match="not a canonical monthly Raw path"):
        build_catalog_row(
            container="raw",
            path=(
                "data-go-kr/stock_price/operation=getstockpriceinfo/"
                "year=2026/month=08/day=13/abc.jsonl.gz"
            ),
            size=1,
            metadata={
                "content_sha256": "a" * 64,
                "batch_hash": "b" * 64,
                "record_count": "1",
            },
            created_at=None,
        )


def test_build_catalog_row_rejects_operation_mismatch() -> None:
    with pytest.raises(ValueError, match="operation metadata/path mismatch"):
        build_catalog_row(
            container="raw",
            path=(
                "data-go-kr/stock_price/operation=getstockpriceinfo/"
                "year=2026/month=08/abc.jsonl.gz"
            ),
            size=1,
            metadata={
                "dataset": "stock_price",
                "operation": "differentOperation",
                "content_sha256": "a" * 64,
                "batch_hash": "b" * 64,
                "record_count": "1",
            },
            created_at=None,
        )
