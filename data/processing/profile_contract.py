"""Raw profile JSON에서 안전한 Processed 타입 계약을 만든다."""
from __future__ import annotations

from typing import Any


def infer_dtype(field: dict[str, Any]) -> str:
    nonempty = int(field.get("nonempty", 0))
    if nonempty == 0:
        return "string"
    if float(field.get("yyyymmdd_rate_nonempty", 0)) == 1.0:
        return "date"
    if float(field.get("integer_rate_nonempty", 0)) == 1.0:
        return "integer"
    if float(field.get("numeric_rate_nonempty", 0)) == 1.0:
        return "number"
    return "string"
