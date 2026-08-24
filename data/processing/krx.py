"""KRX 원문 field를 서비스용 canonical row로 변환한다."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Any


STOCK_CODE_PATTERN = re.compile(r"^\d{6}$")


def _date(value: object) -> date:
    text = str(value)
    if len(text) != 8 or not text.isdigit():
        raise ValueError("invalid KRX date")
    return date(int(text[:4]), int(text[4:6]), int(text[6:]))


def _stock_code(value: object) -> str:
    text = str(value).strip()
    if not STOCK_CODE_PATTERN.fullmatch(text):
        raise ValueError("invalid KRX stock code")
    return text


def _decimal(value: object, *, required: bool = False) -> Decimal | None:
    text = str(value).replace(",", "").strip() if value is not None else ""
    if not text:
        if required:
            raise ValueError("required KRX numeric value is missing")
        return None
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid KRX numeric value") from exc
    if not result.is_finite():
        raise ValueError("non-finite KRX numeric value")
    return result


def _integer(value: object, *, required: bool = False) -> int | None:
    number = _decimal(value, required=required)
    return int(number) if number is not None else None


def stock_master_rows(items: list[dict[str, Any]], *, market: str, as_of: date) -> list[dict[str, Any]]:
    """KRX 종목기본정보를 6자리 종목코드를 보존해 정규화한다."""

    rows: list[dict[str, Any]] = []
    for item in items:
        source_market = str(item.get("MKT_TP_NM") or market).strip().upper()
        if source_market not in {"KOSPI", "KOSDAQ"}:
            raise ValueError("unsupported KRX market")
        rows.append({
            "stock_code": _stock_code(item.get("ISU_SRT_CD")),
            "isin_code": str(item.get("ISU_CD") or "").strip() or None,
            "stock_name": str(item.get("ISU_ABBRV") or item.get("ISU_NM") or "").strip(),
            "stock_name_full": str(item.get("ISU_NM") or "").strip() or None,
            "stock_name_eng": str(item.get("ISU_ENG_NM") or "").strip() or None,
            "market": source_market,
            "listing_date": _date(item["LIST_DD"]) if item.get("LIST_DD") else None,
            "listed_shares": _integer(item.get("LIST_SHRS")),
            "security_type": str(item.get("SECUGRP_NM") or item.get("KIND_STKCERT_TP_NM") or "").strip() or None,
            "sector": str(item.get("SECT_TP_NM") or "").strip() or None,
            "source": "KRX",
            "as_of": as_of,
        })
    if any(not row["stock_name"] for row in rows):
        raise ValueError("KRX stock name is required")
    return rows


def stock_price_rows(items: list[dict[str, Any]], *, market: str, as_of: date) -> list[dict[str, Any]]:
    """KRX 일별매매정보를 서비스 OHLCV와 시가총액 row로 변환한다."""

    rows: list[dict[str, Any]] = []
    for item in items:
        source_market = str(item.get("MKT_NM") or market).strip().upper()
        if source_market not in {"KOSPI", "KOSDAQ"}:
            raise ValueError("unsupported KRX market")
        rows.append({
            "stock_code": _stock_code(item.get("ISU_CD")),
            "trade_date": _date(item.get("BAS_DD")),
            "open_price": _decimal(item.get("TDD_OPNPRC"), required=True),
            "high_price": _decimal(item.get("TDD_HGPRC"), required=True),
            "low_price": _decimal(item.get("TDD_LWPRC"), required=True),
            "close_price": _decimal(item.get("TDD_CLSPRC"), required=True),
            "change_amount": _decimal(item.get("CMPPREVDD_PRC")),
            "change_rate": _decimal(item.get("FLUC_RT")),
            "volume": _integer(item.get("ACC_TRDVOL"), required=True),
            "trading_value": _decimal(item.get("ACC_TRDVAL")),
            "market_cap": _decimal(item.get("MKTCAP")),
            "listed_shares": _integer(item.get("LIST_SHRS")),
            "market": source_market,
            "source": "KRX",
            "as_of": as_of,
        })
    return rows


def market_index_rows(items: list[dict[str, Any]], *, market: str, as_of: date) -> list[dict[str, Any]]:
    """KRX 지수 시계열을 이름 기반의 안정적인 식별자로 정규화한다."""

    rows: list[dict[str, Any]] = []
    for item in items:
        index_name = str(item.get("IDX_NM") or "").strip()
        index_class = str(item.get("IDX_CLSS") or market).strip().upper()
        if not index_name:
            raise ValueError("KRX index name is required")
        rows.append({
            "index_code": f"{market}:{index_class}:{index_name}",
            "index_name": index_name,
            "market": market,
            "trade_date": _date(item.get("BAS_DD")),
            "open_value": _decimal(item.get("OPNPRC_IDX")),
            "high_value": _decimal(item.get("HGPRC_IDX")),
            "low_value": _decimal(item.get("LWPRC_IDX")),
            "close_value": _decimal(item.get("CLSPRC_IDX"), required=True),
            "change_amount": _decimal(item.get("CMPPREVDD_IDX")),
            "change_rate": _decimal(item.get("FLUC_RT")),
            "volume": _integer(item.get("ACC_TRDVOL")),
            "trading_value": _decimal(item.get("ACC_TRDVAL")),
            "market_cap": _decimal(item.get("MKTCAP")),
            "source": "KRX",
            "as_of": as_of,
        })
    return rows

