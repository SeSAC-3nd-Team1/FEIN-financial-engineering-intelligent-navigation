"""Raw API 필드를 Processed/Feature 레이어의 표준 이름과 타입으로 연결한다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

_CAMEL_BOUNDARY_1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_BOUNDARY_2 = re.compile(r"([a-z0-9])([A-Z])")
_UNSAFE = re.compile(r"[^A-Za-z0-9]+")


def snake_case(value: str) -> str:
    """외부 API camelCase 이름을 안정적인 snake_case 이름으로 바꾼다."""

    value = _CAMEL_BOUNDARY_1.sub(r"\1_\2", value)
    value = _CAMEL_BOUNDARY_2.sub(r"\1_\2", value)
    return _UNSAFE.sub("_", value).strip("_").lower()


@dataclass(frozen=True)
class CoreOperation:
    """모델링에 직접 쓰는 핵심 operation의 이름/타입 계약이다."""

    dataset: str
    operation: str
    aliases: Mapping[str, str]
    type_overrides: Mapping[str, str] = field(default_factory=dict)


STOCK_PRICE = CoreOperation(
    "stock_price",
    "getstockpriceinfo",
    {
        "basDt": "trade_date",
        "srtnCd": "stock_code",
        "isinCd": "isin_code",
        "itmsNm": "stock_name",
        "mrktCtg": "market_category",
        "clpr": "close_price",
        "vs": "price_change",
        "fltRt": "change_rate",
        "mkp": "open_price",
        "hipr": "high_price",
        "lopr": "low_price",
        "trqu": "volume",
        "trPrc": "trading_value",
        "lstgStCnt": "listed_shares",
        "mrktTotAmt": "market_cap",
    },
    {
        # 종목코드는 선행 0이 의미를 가지므로 숫자처럼 보여도 문자열로 유지한다.
        "srtnCd": "string",
        "isinCd": "string",
    },
)

STOCK_MASTER = CoreOperation(
    "stock_master",
    "getiteminfo",
    {
        "basDt": "reference_date",
        "srtnCd": "stock_code",
        "isinCd": "isin_code",
        "itmsNm": "stock_name",
        "mrktCtg": "market_category",
        "corpNm": "corporation_name",
        "crno": "corporation_number",
    },
    {
        "srtnCd": "string",
        "isinCd": "string",
        "crno": "string",
    },
)

MARKET_INDEX = CoreOperation(
    "market_index",
    "getstockmarketindex",
    {
        "basDt": "trade_date",
        "idxNm": "index_name",
        "idxCsf": "index_category",
        "clpr": "close_index",
        "vs": "index_change",
        "fltRt": "index_change_rate",
        "mkp": "open_index",
        "hipr": "high_index",
        "lopr": "low_index",
        "trqu": "volume",
        "trPrc": "trading_value",
        "lstgMrktTotAmt": "market_cap",
    },
)

FINANCIAL_SUMMARY = CoreOperation(
    "financial_statement",
    "getsummfinastat_v2",
    {
        "basDt": "base_date",
        "crno": "corporation_number",
        "bizYear": "business_year",
        "curCd": "currency",
        "fnclDcd": "financial_division_code",
        "fnclDcdNm": "financial_division_name",
        "enpSaleAmt": "sales",
        "enpBzopPft": "operating_profit",
        "enpCrtmNpf": "net_income",
        "enpTastAmt": "total_assets",
        "enpTdbtAmt": "total_liabilities",
        "enpTcptAmt": "total_equity",
        "enpCptlAmt": "capital",
        "fnclDebtRto": "reported_debt_ratio",
        "iclsPalClcAmt": "comprehensive_income",
    },
    {
        "crno": "string",
        "fnclDcd": "string",
        "curCd": "string",
    },
)

FINANCIAL_ACCOUNT_ALIASES = {
    "basDt": "base_date",
    "crno": "corporation_number",
    "bizYear": "business_year",
    "acitId": "account_id",
    "acitNm": "account_name",
    "curCd": "currency",
    "fnclDcd": "financial_division_code",
    "fnclDcdNm": "financial_division_name",
    "crtmAcitAmt": "current_amount",
    "pvtrAcitAmt": "previous_amount",
    "bpvtrAcitAmt": "before_previous_amount",
    "thqrAcitAmt": "quarter_amount",
    "lsqtAcitAmt": "last_quarter_amount",
}
FINANCIAL_ACCOUNT_TYPES = {
    "crno": "string",
    "acitId": "string",
    "fnclDcd": "string",
    "curCd": "string",
}
BALANCE_SHEET = CoreOperation(
    "financial_statement",
    "getbs_v2",
    FINANCIAL_ACCOUNT_ALIASES,
    FINANCIAL_ACCOUNT_TYPES,
)
INCOME_STATEMENT = CoreOperation(
    "financial_statement",
    "getincostat_v2",
    FINANCIAL_ACCOUNT_ALIASES,
    FINANCIAL_ACCOUNT_TYPES,
)

CORE_BY_KEY = {
    (item.dataset, item.operation): item
    for item in (
        STOCK_PRICE,
        STOCK_MASTER,
        MARKET_INDEX,
        FINANCIAL_SUMMARY,
        BALANCE_SHEET,
        INCOME_STATEMENT,
    )
}

# 핵심 operation 밖에서도 코드/식별자 필드를 정수화하지 않기 위한 보수적 규칙이다.
_IDENTIFIER_EXACT = {
    "crno",
    "isinCd",
    "srtnCd",
    "itmsShrtnCd",
    "corpCode",
    "stockCode",
    "acitId",
}
_IDENTIFIER_SUFFIXES = ("Cd", "Dcd", "Kcd", "Rcd", "Id")


def canonical_name(dataset: str, operation: str, raw_field: str) -> str:
    """핵심 계약이 있으면 의미 있는 이름을 쓰고, 나머지는 snake_case로 보존한다."""

    core = CORE_BY_KEY.get((dataset, operation.lower()))
    if core and raw_field in core.aliases:
        return core.aliases[raw_field]
    return snake_case(raw_field)


def canonical_dtype(
    dataset: str,
    operation: str,
    raw_field: str,
    inferred_dtype: str,
) -> str:
    """프로파일 추론보다 식별자/코드의 업무 의미를 우선해 최종 타입을 결정한다."""

    core = CORE_BY_KEY.get((dataset, operation.lower()))
    if core and raw_field in core.type_overrides:
        return core.type_overrides[raw_field]
    if raw_field in _IDENTIFIER_EXACT or raw_field.endswith(_IDENTIFIER_SUFFIXES):
        return "string"
    return inferred_dtype
