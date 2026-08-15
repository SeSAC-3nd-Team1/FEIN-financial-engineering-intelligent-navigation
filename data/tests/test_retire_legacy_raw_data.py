from scripts.retire_legacy_raw_data import RecordIdBitmap, validate_raw_record
from storage.raw import payload_hash


def _record(*, record_id=7, bas_dt="20260813"):
    payload = {"basDt": bas_dt, "srtnCd": "005930", "clpr": "74200"}
    return {
        "dataset": "stock_price",
        "operation": "getStockPriceInfo",
        "payloadHash": payload_hash(payload),
        "payload": payload,
        "legacy": {"recordId": record_id},
    }


def test_record_id_bitmap_detects_duplicates() -> None:
    bitmap = RecordIdBitmap(10)
    assert bitmap.add(1) is True
    assert bitmap.add(10) is True
    assert bitmap.add(1) is False


def test_validate_raw_record_accepts_matching_legacy_record() -> None:
    record_id, observed_hash, payload = validate_raw_record(
        _record(),
        path_dataset="stock_price",
        path_operation="getstockpriceinfo",
        path_year=2026,
        path_month=8,
    )
    assert record_id == 7
    assert observed_hash == payload_hash(payload)


def test_validate_raw_record_allows_blob_only_record() -> None:
    record = _record()
    record.pop("legacy")
    record_id, _, _ = validate_raw_record(
        record,
        path_dataset="stock_price",
        path_operation="getstockpriceinfo",
        path_year=2026,
        path_month=8,
    )
    assert record_id is None


def test_validate_raw_record_rejects_partition_mismatch() -> None:
    try:
        validate_raw_record(
            _record(bas_dt="20260731"),
            path_dataset="stock_price",
            path_operation="getstockpriceinfo",
            path_year=2026,
            path_month=8,
        )
    except ValueError as exc:
        assert "partition mismatch" in str(exc)
    else:
        raise AssertionError("expected partition mismatch to fail")


def test_validate_raw_record_rejects_payload_hash_mismatch() -> None:
    record = _record()
    record["payloadHash"] = "0" * 64
    try:
        validate_raw_record(
            record,
            path_dataset="stock_price",
            path_operation="getstockpriceinfo",
            path_year=2026,
            path_month=8,
        )
    except ValueError as exc:
        assert "payload hash mismatch" in str(exc)
    else:
        raise AssertionError("expected payload hash mismatch to fail")
