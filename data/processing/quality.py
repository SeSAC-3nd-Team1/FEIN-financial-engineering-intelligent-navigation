"""Raw → Processed 변환 시 적용하는 품질 규칙과 집계."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

@dataclass
class QualityResult:
    accepted: int = 0
    rejected: int = 0
    reasons: dict[str,int] = field(default_factory=dict)
    conversion_errors: dict[str,int] = field(default_factory=dict)
    def reject(self, reason: str) -> None:
        self.rejected += 1; self.reasons[reason] = self.reasons.get(reason,0)+1
    def conversion_error(self, field: str) -> None:
        self.conversion_errors[field] = self.conversion_errors.get(field,0)+1

def validate_payload(payload: dict[str,Any]) -> str | None:
    bas_dt = payload.get("basDt")
    if bas_dt is None or str(bas_dt).strip() == "": return "missing_basDt"
    try: datetime.strptime(str(bas_dt).strip(), "%Y%m%d")
    except ValueError: return "invalid_basDt"
    return None
validate_raw_record = validate_payload
