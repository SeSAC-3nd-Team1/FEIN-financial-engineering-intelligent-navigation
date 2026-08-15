"""Landing-table and normalized loaders for public-data responses."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from collectors.public_data_config import ApiOperation
from db.models import MarketIndexDaily, PublicDataRecord, RawDataObject, StockMaster
from loaders.stocks import load_stock_master, load_stock_prices, normalize_stock_code
from loaders.upsert import upsert_dataframe, upsert_rows
from storage import BlobObject, RawBatch


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def parse_decimal(value: Any) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"-", "N/A"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_integer(value: Any) -> int | None:
    number = parse_decimal(value)
    return int(number) if number is not None else None


def _payload_hash(item: dict[str, Any]) -> str:
    canonical = json.dumps(
        item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def landing_rows(
    operation: ApiOperation, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Extract common search keys while retaining every original response field."""

    return [
        {
            "dataset": operation.dataset,
            "operation": operation.name,
            "payload_hash": _payload_hash(item),
            "reference_date": parse_date(item.get("basDt")),
            "stock_code": normalize_stock_code(
                item.get("srtnCd") or item.get("itmsCd")
            ),
            "isin": item.get("isinCd"),
            "corporation_registration_number": item.get("crno"),
            "corporation_name": item.get("corpNm") or item.get("isinCdNm"),
            "payload": item,
        }
        for item in items
    ]


def load_landing_items(
    session: Session, operation: ApiOperation, items: list[dict[str, Any]]
) -> int:
    return upsert_rows(
        session,
        PublicDataRecord,
        landing_rows(operation, items),
        conflict_columns=["dataset", "operation", "payload_hash"],
        update_columns=["reference_date"],
    )


def record_raw_data_object(
    session: Session,
    operation: ApiOperation,
    blob: BlobObject,
    batch: RawBatch,
    *,
    source: str,
    range_start: date | None = None,
    range_end: date | None = None,
) -> int:
    """Record a Blob reference without copying raw payloads into PostgreSQL."""

    statement = (
        insert(RawDataObject.__table__)
        .values(
            dataset=operation.dataset,
            operation=operation.name,
            source=source,
            container=blob.container,
            blob_path=blob.path,
            content_sha256=batch.content_sha256,
            batch_hash=batch.batch_hash,
            record_count=batch.record_count,
            range_start=range_start,
            range_end=range_end,
            file_size=blob.size,
            compression="gzip",
            status="available",
        )
        .on_conflict_do_nothing(index_elements=["container", "blob_path"])
    )
    result = session.execute(statement)
    return max(result.rowcount, 0)


def normalize_stock_master(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "reference_date": parse_date(item.get("basDt")),
            "stock_code": normalize_stock_code(item.get("srtnCd")),
            "isin": item.get("isinCd") or None,
            "market_type": item.get("mrktCtg") or "UNKNOWN",
            "stock_name": item.get("itmsNm") or "UNKNOWN",
            "corporation_registration_number": item.get("crno") or None,
            "corporation_name": item.get("corpNm") or None,
            "source": "DATA_GO_KR_KRX_LISTED",
            "source_payload": item,
        }
        for item in items
        if item.get("basDt") and item.get("srtnCd")
    ]
    return pd.DataFrame(rows)


def normalize_stock_prices(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "stock_code": normalize_stock_code(item.get("srtnCd")),
            "trade_date": parse_date(item.get("basDt")),
            "open_price": parse_decimal(item.get("mkp")),
            "high_price": parse_decimal(item.get("hipr")),
            "low_price": parse_decimal(item.get("lopr")),
            "close_price": parse_decimal(item.get("clpr")),
            "volume": parse_integer(item.get("trqu")),
            "trading_value": parse_decimal(item.get("trPrc")),
            "price_type": "unadjusted",
            "source": "DATA_GO_KR_STOCK_PRICE",
            "source_payload": item,
        }
        for item in items
        if item.get("basDt") and item.get("srtnCd") and item.get("clpr")
    ]
    return pd.DataFrame(rows)


def ensure_price_stock_masters(session: Session, items: list[dict[str, Any]]) -> int:
    """Add securities present in the price feed but absent from KRX master.

    The price service includes preferred shares and newer code formats that the
    listed-item service may omit. Existing richer master records are never
    overwritten.
    """

    rows = [
        {
            "reference_date": parse_date(item.get("basDt")),
            "stock_code": normalize_stock_code(item.get("srtnCd")),
            "isin": item.get("isinCd") or None,
            "market_type": item.get("mrktCtg") or "UNKNOWN",
            "stock_name": item.get("itmsNm") or "UNKNOWN",
            "source": "DATA_GO_KR_STOCK_PRICE_DERIVED_MASTER",
            "source_payload": item,
        }
        for item in items
        if item.get("basDt") and item.get("srtnCd")
    ]
    if not rows:
        return 0
    inserted = 0
    for start in range(0, len(rows), 1_000):
        statement = (
            insert(StockMaster.__table__)
            .values(rows[start : start + 1_000])
            .on_conflict_do_nothing()
        )
        result = session.execute(statement)
        inserted += max(result.rowcount, 0)
    return inserted


def normalize_market_indices(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "index_code": f"{item.get('idxCsf') or 'UNKNOWN'}:{item.get('idxNm')}",
            "trade_date": parse_date(item.get("basDt")),
            "open_value": parse_decimal(item.get("mkp")),
            "high_value": parse_decimal(item.get("hipr")),
            "low_value": parse_decimal(item.get("lopr")),
            "close_value": parse_decimal(item.get("clpr")),
            "change_rate": parse_decimal(item.get("fltRt")),
            "source": "DATA_GO_KR_MARKET_INDEX",
            "source_payload": item,
        }
        for item in items
        if item.get("basDt") and item.get("idxNm") and item.get("clpr")
    ]
    return pd.DataFrame(rows)


def load_normalized_items(
    session: Session, operation: ApiOperation, items: list[dict[str, Any]]
) -> int:
    """Populate established domain tables for operations with stable mappings."""

    if operation.name == "getItemInfo":
        frame = normalize_stock_master(items)
        return load_stock_master(session, frame) if not frame.empty else 0
    if operation.name == "getStockPriceInfo":
        ensure_price_stock_masters(session, items)
        frame = normalize_stock_prices(items)
        return load_stock_prices(session, frame) if not frame.empty else 0
    if operation.name == "getStockMarketIndex":
        frame = normalize_market_indices(items)
        return (
            upsert_dataframe(
                session,
                MarketIndexDaily,
                frame,
                conflict_columns=["index_code", "trade_date"],
            )
            if not frame.empty
            else 0
        )
    return 0
