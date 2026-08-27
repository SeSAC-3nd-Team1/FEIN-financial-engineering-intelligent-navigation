"""OpenDART 응답을 PostgreSQL 적재 행과 핵심 재무지표로 정규화한다."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import re
from typing import Any

REPORT_QUARTERS = {"11013": "Q1", "11012": "Q2", "11014": "Q3", "11011": "FY"}
DIVIDEND_METRICS = {
    "주당현금배당금(원)": "dividend_per_share",
    "현금배당수익률(%)": "reported_dividend_yield",
    "현금배당금총액(백만원)": "total_dividend",
    "현금배당성향(%)": "dividend_payout_ratio",
    "(연결)현금배당성향(%)": "dividend_payout_ratio",
}

# IFRS account_id를 우선하고, 회사별 확장 계정은 한국어 계정명 후보로 보완한다.
METRIC_ALIASES: dict[str, tuple[set[str], set[str]]] = {
    "revenue": (
        {"ifrs-full_Revenue", "ifrs-full_RevenueFromContractsWithCustomers"},
        {"매출액", "수익(매출액)", "영업수익"},
    ),
    "operating_income": ({"dart_OperatingIncomeLoss"}, {"영업이익", "영업이익(손실)"}),
    "net_income": (
        {"ifrs-full_ProfitLoss"},
        {"당기순이익", "당기순이익(손실)", "분기순이익"},
    ),
    "total_assets": ({"ifrs-full_Assets"}, {"자산총계"}),
    "total_liabilities": ({"ifrs-full_Liabilities"}, {"부채총계"}),
    "total_equity": ({"ifrs-full_Equity"}, {"자본총계"}),
    "operating_cash_flow": (
        {"ifrs-full_CashFlowsFromUsedInOperatingActivities"},
        {"영업활동현금흐름"},
    ),
    "investing_cash_flow": (
        {"ifrs-full_CashFlowsFromUsedInInvestingActivities"},
        {"투자활동현금흐름"},
    ),
    "financing_cash_flow": (
        {"ifrs-full_CashFlowsFromUsedInFinancingActivities"},
        {"재무활동현금흐름"},
    ),
}


def parse_date(value: Any) -> date | None:
    """OpenDART YYYYMMDD 날짜를 nullable date로 바꾼다."""

    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def parse_amount(value: Any) -> Decimal | None:
    """쉼표, 공백, 괄호 음수 표기를 Decimal로 안전하게 바꾼다."""

    text = str(value or "").strip().replace(",", "").replace(" ", "")
    if not text or text == "-":
        return None
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _normalized_label(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _stock_kind(value: Any) -> str | None:
    """OpenDART 주식 종류를 UPSERT에 쓸 수 있는 안정적인 식별자로 만든다."""

    raw = _normalized_label(value)
    if not raw or raw == "-":
        return None
    if raw == "우선주":
        return "PREFERRED"
    if "우선" in raw:
        # 세부 우선주 종류는 사람이 식별할 수 있는 원문을 우선 사용한다. 컬럼 한도를
        # 넘을 때만 원문 전체의 digest로 재수집 가능한 충돌키를 만든다.
        if len(raw) <= 20:
            return raw
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10].upper()
        return f"PREFERRED_{digest}"
    if "보통" in raw:
        return "COMMON"
    return raw[:20]


def dividend_rows(
    payload: dict[str, Any],
    *,
    stock_code: str,
    corp_code: str,
    business_year: str,
    report_code: str,
    collected_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """사업보고서 ``alotMatter``의 연간 thstrm 값을 주식 종류별 행으로 만든다.

    사업보고서 응답의 ``주당 현금배당금(원)``은 중간·분기배당을 포함한 해당 사업연도
    연간 DPS다. 따라서 여러 공시를 합산하지 않고 11011 응답의 현재기(``thstrm``)를 쓴다.
    총액·성향은 stock_knd가 '-'인 공통 지표라 각 종류 행에 동일하게 연결한다.
    """

    if report_code != "11011":
        raise ValueError("dividend normalization requires annual report code 11011")
    items = payload.get("list", [])
    if not isinstance(items, list):
        raise ValueError("OpenDART dividend list must be an array")

    common: dict[str, Decimal | None] = {}
    by_kind: dict[str, dict[str, Any]] = {}
    for item in items:
        metric = DIVIDEND_METRICS.get(_normalized_label(item.get("se")))
        if metric is None:
            continue
        value = parse_amount(item.get("thstrm"))
        kind = _stock_kind(item.get("stock_knd"))
        if kind is None:
            if (
                metric in {"total_dividend", "dividend_payout_ratio"}
                and metric not in common
            ):
                common[metric] = value
            continue
        target = by_kind.setdefault(
            kind,
            {
                "stock_kind": kind,
                "raw_stock_kind": str(item.get("stock_knd") or "").strip() or None,
                "receipt_no": str(item.get("rcept_no") or "").strip() or None,
                "settlement_date": parse_date(
                    str(item.get("stlm_dt") or "").replace("-", "")
                ),
            },
        )
        # 같은 공식 지표가 중복돼도 합산하지 않는다. alotMatter의 thstrm은 연간값이다.
        if metric not in target or target[metric] is None:
            target[metric] = value

    timestamp = collected_at or datetime.now().astimezone()
    rows: list[dict[str, Any]] = []
    for values in by_kind.values():
        if (
            values.get("dividend_per_share") is None
            and values.get("reported_dividend_yield") is None
        ):
            continue
        rows.append(
            {
                "stock_code": stock_code,
                "corp_code": corp_code,
                "business_year": business_year,
                "report_code": report_code,
                "stock_kind": values["stock_kind"],
                "raw_stock_kind": values.get("raw_stock_kind"),
                "dividend_per_share": values.get("dividend_per_share"),
                "reported_dividend_yield": values.get("reported_dividend_yield"),
                "total_dividend": common.get("total_dividend"),
                "dividend_payout_ratio": common.get("dividend_payout_ratio"),
                "receipt_no": values.get("receipt_no"),
                "settlement_date": values.get("settlement_date"),
                "source": "OpenDART_ALOT_MATTER",
                "collected_at": timestamp,
            }
        )
    return rows


def corp_code_rows(records: list[Any]) -> list[dict[str, Any]]:
    """CorpCodeRecord 목록을 companies UPSERT 행으로 변환한다."""

    return [
        {
            "corp_code": record.corp_code,
            "corp_name": record.corp_name,
            "corp_name_eng": record.corp_name_eng,
            "stock_code": record.stock_code,
            "dart_modify_date": parse_date(record.modify_date),
        }
        for record in records
    ]


def company_row(payload: dict[str, Any]) -> dict[str, Any]:
    """기업개황 필드명을 내부 기업 마스터 컬럼에 매핑한다."""

    return {
        "corp_code": str(payload["corp_code"]),
        "corp_name": str(payload["corp_name"]),
        "corp_name_eng": payload.get("corp_name_eng") or None,
        "stock_name": payload.get("stock_name") or None,
        "stock_code": payload.get("stock_code") or None,
        "market": payload.get("corp_cls") or None,
        "ceo_name": payload.get("ceo_nm") or None,
        "jurir_no": payload.get("jurir_no") or None,
        "bizr_no": payload.get("bizr_no") or None,
        "address": payload.get("adres") or None,
        "homepage_url": payload.get("hm_url") or None,
        "ir_url": payload.get("ir_url") or None,
        "phone_number": payload.get("phn_no") or None,
        "industry_code": payload.get("induty_code") or None,
        "established_date": parse_date(payload.get("est_dt")),
        "accounting_month": payload.get("acc_mt") or None,
    }


def financial_account_rows(
    payload: dict[str, Any], *, stock_code: str
) -> list[dict[str, Any]]:
    """재무 응답 list를 계정별 원본 정제 행으로 바꾼다."""

    rows: list[dict[str, Any]] = []
    for item in payload.get("list", []):
        account_name = str(item.get("account_nm") or "").strip()
        account_id = str(item.get("account_id") or "").strip()
        if not account_id:
            account_id = f"name:{re.sub(r'\s+', '', account_name)}"
        rows.append(
            {
                "corp_code": str(
                    item.get("corp_code") or payload.get("corp_code") or ""
                ),
                "stock_code": stock_code,
                "business_year": str(item.get("bsns_year") or ""),
                "report_code": str(item.get("reprt_code") or ""),
                "fs_div": str(item.get("fs_div") or ""),
                "sj_div": str(item.get("sj_div") or ""),
                "account_id": account_id,
                "account_name": account_name,
                "current_amount": parse_amount(item.get("thstrm_amount")),
                "previous_amount": parse_amount(item.get("frmtrm_amount")),
                "currency": str(item.get("currency") or "KRW"),
            }
        )
    return rows


def financial_summary_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """계정 ID 우선 규칙으로 한 보고서의 핵심 재무지표를 만든다."""

    if not rows:
        return None
    base = rows[0]
    summary: dict[str, Any] = {
        "corp_code": base["corp_code"],
        "stock_code": base["stock_code"],
        "business_year": base["business_year"],
        "report_code": base["report_code"],
        "quarter": REPORT_QUARTERS.get(base["report_code"], base["report_code"]),
        "fs_div": base["fs_div"],
    }
    for metric, (ids, names) in METRIC_ALIASES.items():
        matched = next((row for row in rows if row["account_id"] in ids), None)
        if matched is None:
            matched = next(
                (
                    row
                    for row in rows
                    if re.sub(r"\s+", "", row["account_name"]) in names
                ),
                None,
            )
        summary[metric] = matched["current_amount"] if matched else None
    return summary


def disclosure_rows(
    payload: dict[str, Any], *, stock_code: str
) -> list[dict[str, Any]]:
    """공시검색 응답을 receipt_no 충돌키 기반 적재 행으로 바꾼다."""

    return [
        {
            "receipt_no": str(item["rcept_no"]),
            "corp_code": str(item["corp_code"]),
            "stock_code": item.get("stock_code") or stock_code,
            "corp_name": str(item["corp_name"]),
            "report_name": str(item["report_nm"]),
            "filer_name": item.get("flr_nm") or None,
            "receipt_date": parse_date(item.get("rcept_dt")),
            "remarks": item.get("rm") or None,
        }
        for item in payload.get("list", [])
        if item.get("rcept_no") and parse_date(item.get("rcept_dt"))
    ]
