"""Raw → Processed 변환 시 적용하는 품질 규칙과 집계."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class QualityResult:
    accepted: int = 0
    rejected: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    conversion_errors: dict[str, int] = field(default_factory=dict)

    def reject(self, reason: str) -> None:
        self.rejected += 1
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    def conversion_error(self, field: str) -> None:
        self.conversion_errors[field] = self.conversion_errors.get(field, 0) + 1


_REQUIRED_FIELDS: dict[tuple[str, str], tuple[str, ...]] = {
    ("stock_price", "getstockpriceinfo"): (
        "basDt",
        "srtnCd",
        "isinCd",
        "clpr",
        "trqu",
    ),
    ("stock_master", "getiteminfo"): (
        "basDt",
        "srtnCd",
        "isinCd",
        "crno",
    ),
    ("market_index", "getstockmarketindex"): (
        "basDt",
        "idxNm",
        "clpr",
    ),
    ("financial_statement", "getsummfinastat_v2"): (
        "basDt",
        "crno",
        "bizYear",
        "fnclDcd",
    ),
}


def validate_payload(
    payload: dict[str, Any],
    dataset: str | None = None,
    operation: str | None = None,
) -> str | None:
    """공통 날짜 무결성과 핵심 모델링 operation의 최소 필드를 검증한다."""

    bas_dt = payload.get("basDt")
    if bas_dt is None or str(bas_dt).strip() == "":
        return "missing_basDt"
    try:
        datetime.strptime(str(bas_dt).strip(), "%Y%m%d")
    except ValueError:
        return "invalid_basDt"

    if dataset and operation:
        required = _REQUIRED_FIELDS.get((dataset, operation.lower()), ())
        for field_name in required:
            value = payload.get(field_name)
            if value is None or str(value).strip() == "":
                return f"missing_required:{field_name}"

    return None


validate_raw_record = validate_payload
