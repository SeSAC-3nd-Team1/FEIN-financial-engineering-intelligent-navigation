"""Raw profile JSON에서 안전한 Processed 타입 계약을 만든다."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1
_FLOAT64_MAX = Decimal(str(float.fromhex("0x1.fffffffffffffp+1023")))


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def infer_dtype(field: dict[str, Any]) -> str:
    """실제 관측 분포를 바탕으로 정보손실 위험이 낮은 타입을 고른다.

    숫자처럼 보이더라도 BIGINT/float64 표현 범위를 벗어나면 원문 문자열을 보존한다.
    이런 값은 공시의 조합형/비정형 필드에서 실제로 관측됐기 때문에 변환 실패보다 보존을
    우선한다.
    """

    nonempty = int(field.get("nonempty", 0))
    if nonempty == 0:
        return "string"

    if float(field.get("yyyymmdd_rate_nonempty", 0)) == 1.0:
        return "date"

    minimum = _decimal(field.get("min_number"))
    maximum = _decimal(field.get("max_number"))

    if float(field.get("integer_rate_nonempty", 0)) == 1.0:
        if minimum is None or maximum is None:
            return "string"
        if minimum < _INT64_MIN or maximum > _INT64_MAX:
            return "string"
        return "integer"

    if float(field.get("numeric_rate_nonempty", 0)) == 1.0:
        if minimum is None or maximum is None:
            return "string"
        if abs(minimum) > _FLOAT64_MAX or abs(maximum) > _FLOAT64_MAX:
            return "string"
        return "number"

    return "string"
