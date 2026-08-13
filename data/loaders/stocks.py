"""Stock-code-aware DataFrame loaders."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import StockMaster, StockPriceDaily
from loaders.upsert import upsert_dataframe


STOCK_MASTER_COLUMN_MAPPING = {
    "기준일자": "reference_date",
    "종목코드": "stock_code",
    "시장구분": "market_type",
    "종목명": "stock_name",
    "법인등록번호": "corporation_registration_number",
    "법인명": "corporation_name",
}

STOCK_PRICE_COLUMN_MAPPING = {
    "종목코드": "stock_code",
    "날짜": "trade_date",
    "시가": "open_price",
    "고가": "high_price",
    "저가": "low_price",
    "종가": "close_price",
    "거래량": "volume",
    "거래대금": "trading_value",
}


def load_stock_master(session: Session, frame: pd.DataFrame) -> int:
    """UPSERT a normalized or Korean-column KRX stock master frame."""

    normalized = frame.rename(columns=STOCK_MASTER_COLUMN_MAPPING).copy()
    if "stock_code" not in normalized.columns:
        raise ValueError("stock_code is required")
    normalized["stock_code"] = normalized["stock_code"].astype(str).str.zfill(6)
    return upsert_dataframe(
        session,
        StockMaster,
        normalized,
        conflict_columns=["stock_code"],
    )


def attach_stock_ids(session: Session, frame: pd.DataFrame) -> pd.DataFrame:
    """Replace ``stock_code`` with the stable internal foreign key."""

    if "stock_code" not in frame.columns:
        raise ValueError("stock_code is required to resolve stock_id")
    codes = frame["stock_code"].astype(str).str.zfill(6).unique().tolist()
    stock_ids = dict(
        session.execute(
            select(StockMaster.stock_code, StockMaster.stock_id).where(
                StockMaster.stock_code.in_(codes)
            )
        ).all()
    )
    missing = sorted(set(codes) - stock_ids.keys())
    if missing:
        raise ValueError(f"stock_master rows must be loaded first: {missing}")
    result = frame.copy()
    result["stock_code"] = result["stock_code"].astype(str).str.zfill(6)
    result["stock_id"] = result["stock_code"].map(stock_ids)
    return result.drop(columns=["stock_code"])


def load_stock_prices(session: Session, frame: pd.DataFrame) -> int:
    """Resolve stock codes and UPSERT daily OHLCV rows."""

    normalized = frame.rename(columns=STOCK_PRICE_COLUMN_MAPPING).copy()
    if "price_type" not in normalized.columns:
        normalized["price_type"] = "unadjusted"
    normalized = attach_stock_ids(session, normalized)
    return upsert_dataframe(
        session,
        StockPriceDaily,
        normalized,
        conflict_columns=["stock_id", "trade_date", "price_type"],
    )
