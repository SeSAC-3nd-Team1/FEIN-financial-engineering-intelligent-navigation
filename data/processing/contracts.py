"""Raw API 필드를 Processed/Feature 레이어의 표준 이름과 타입으로 연결한다."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

_CAMEL_BOUNDARY_1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_BOUNDARY_2 = re.compile(r"([a-z0-9])([A-Z])")
_UNSAFE = re.compile(r"[^A-Za-z0-9]+")

def snake_case(value: str) -> str:
    value = _CAMEL_BOUNDARY_1.sub(r"\1_\2", value)
    value = _CAMEL_BOUNDARY_2.sub(r"\1_\2", value)
    return _UNSAFE.sub("_", value).strip("_").lower()

@dataclass(frozen=True)
class CoreOperation:
    dataset: str
    operation: str
    aliases: Mapping[str, str]

STOCK_PRICE = CoreOperation("stock_price", "getstockpriceinfo", {
    "basDt":"trade_date","srtnCd":"stock_code","isinCd":"isin_code","itmsNm":"stock_name",
    "mrktCtg":"market_category","clpr":"close_price","vs":"price_change","fltRt":"change_rate",
    "mkp":"open_price","hipr":"high_price","lopr":"low_price","trqu":"volume",
    "trPrc":"trading_value","lstgStCnt":"listed_shares","mrktTotAmt":"market_cap",
})
MARKET_INDEX = CoreOperation("market_index", "getstockmarketindex", {
    "basDt":"trade_date","idxNm":"index_name","idxCsf":"index_category","clpr":"close_index",
    "vs":"index_change","fltRt":"index_change_rate","mkp":"open_index","hipr":"high_index",
    "lopr":"low_index","trqu":"volume","trPrc":"trading_value","lstgMrktTotAmt":"market_cap",
})
FINANCIAL_SUMMARY = CoreOperation("financial_statement", "getsummfinastat_v2", {
    "basDt":"base_date","crno":"corporation_number","bizYear":"business_year","curCd":"currency",
    "fnclDcd":"financial_division_code","fnclDcdNm":"financial_division_name","enpSaleAmt":"sales",
    "enpBzopPft":"operating_profit","enpCrtmNpf":"net_income","enpTastAmt":"total_assets",
    "enpTdbtAmt":"total_liabilities","enpTcptAmt":"total_equity","enpCptlAmt":"capital",
    "fnclDebtRto":"reported_debt_ratio","iclsPalClcAmt":"comprehensive_income",
})
FINANCIAL_ACCOUNT_ALIASES = {
    "basDt":"base_date","crno":"corporation_number","bizYear":"business_year","acitId":"account_id",
    "acitNm":"account_name","curCd":"currency","fnclDcd":"financial_division_code",
    "fnclDcdNm":"financial_division_name","crtmAcitAmt":"current_amount","pvtrAcitAmt":"previous_amount",
    "bpvtrAcitAmt":"before_previous_amount","thqrAcitAmt":"quarter_amount","lsqtAcitAmt":"last_quarter_amount",
}
BALANCE_SHEET = CoreOperation("financial_statement", "getbs_v2", FINANCIAL_ACCOUNT_ALIASES)
INCOME_STATEMENT = CoreOperation("financial_statement", "getincostat_v2", FINANCIAL_ACCOUNT_ALIASES)
CORE_BY_KEY = {(item.dataset,item.operation):item for item in (STOCK_PRICE,MARKET_INDEX,FINANCIAL_SUMMARY,BALANCE_SHEET,INCOME_STATEMENT)}

def canonical_name(dataset: str, operation: str, raw_field: str) -> str:
    core = CORE_BY_KEY.get((dataset, operation.lower()))
    if core and raw_field in core.aliases:
        return core.aliases[raw_field]
    return snake_case(raw_field)
