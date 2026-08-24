"""OpenDART 응답을 PostgreSQL 적재 행과 핵심 재무지표로 정규화한다."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any


REPORT_QUARTERS = {"11013": "Q1", "11012": "Q2", "11014": "Q3", "11011": "FY"}

# IFRS account_id를 우선하고, 회사별 확장 계정은 한국어 계정명 후보로 보완한다.
METRIC_ALIASES: dict[str, tuple[set[str], set[str]]] = {
    "revenue": (
        {"ifrs-full_Revenue", "ifrs-full_RevenueFromContractsWithCustomers"},
        {"매출액", "수익(매출액)", "영업수익"},
    ),
    "operating_income": ({"dart_OperatingIncomeLoss"}, {"영업이익", "영업이익(손실)"}),
    "net_income": ({"ifrs-full_ProfitLoss"}, {"당기순이익", "당기순이익(손실)", "분기순이익"}),
    "total_assets": ({"ifrs-full_Assets"}, {"자산총계"}),
    "total_liabilities": ({"ifrs-full_Liabilities"}, {"부채총계"}),
    "total_equity": ({"ifrs-full_Equity"}, {"자본총계"}),
    "operating_cash_flow": ({"ifrs-full_CashFlowsFromUsedInOperatingActivities"}, {"영업활동현금흐름"}),
    "investing_cash_flow": ({"ifrs-full_CashFlowsFromUsedInInvestingActivities"}, {"투자활동현금흐름"}),
    "financing_cash_flow": ({"ifrs-full_CashFlowsFromUsedInFinancingActivities"}, {"재무활동현금흐름"}),
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


def corp_code_rows(records: list[Any]) -> list[dict[str, Any]]:
    """CorpCodeRecord 목록을 companies UPSERT 행으로 변환한다."""

    return [{
        "corp_code": record.corp_code,
        "corp_name": record.corp_name,
        "corp_name_eng": record.corp_name_eng,
        "stock_code": record.stock_code,
        "dart_modify_date": parse_date(record.modify_date),
    } for record in records]


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


def financial_account_rows(payload: dict[str, Any], *, stock_code: str) -> list[dict[str, Any]]:
    """재무 응답 list를 계정별 원본 정제 행으로 바꾼다."""

    rows: list[dict[str, Any]] = []
    for item in payload.get("list", []):
        account_name = str(item.get("account_nm") or "").strip()
        account_id = str(item.get("account_id") or "").strip()
        if not account_id:
            account_id = f"name:{re.sub(r'\s+', '', account_name)}"
        rows.append({
            "corp_code": str(item.get("corp_code") or payload.get("corp_code") or ""),
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
        })
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
            matched = next((row for row in rows if re.sub(r"\s+", "", row["account_name"]) in names), None)
        summary[metric] = matched["current_amount"] if matched else None
    return summary


def disclosure_rows(payload: dict[str, Any], *, stock_code: str) -> list[dict[str, Any]]:
    """공시검색 응답을 receipt_no 충돌키 기반 적재 행으로 바꾼다."""

    return [{
        "receipt_no": str(item["rcept_no"]),
        "corp_code": str(item["corp_code"]),
        "stock_code": item.get("stock_code") or stock_code,
        "corp_name": str(item["corp_name"]),
        "report_name": str(item["report_nm"]),
        "filer_name": item.get("flr_nm") or None,
        "receipt_date": parse_date(item.get("rcept_dt")),
        "remarks": item.get("rm") or None,
    } for item in payload.get("list", []) if item.get("rcept_no") and parse_date(item.get("rcept_dt"))]
