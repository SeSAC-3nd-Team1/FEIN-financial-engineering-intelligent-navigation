"""Profile contract를 이용해 Raw payload를 표준 컬럼과 Python scalar로 변환한다."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from processing.contracts import canonical_dtype, canonical_name
from processing.profile_contract import infer_dtype


def _convert(value: Any, dtype: str) -> Any:
    """빈 문자열은 NULL로 바꾸고, 계약 타입에 맞는 Python scalar로 변환한다."""

    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    if dtype == "date":
        try:
            return datetime.strptime(text, "%Y%m%d").date()
        except ValueError:
            return None
    if dtype == "integer":
        try:
            return int(text.replace(",", ""))
        except ValueError:
            return None
    if dtype == "number":
        try:
            return float(Decimal(text.replace(",", "")))
        except InvalidOperation:
            return None
    return text


def build_operation_contract(
    profile_operation: dict[str, Any],
    dataset: str,
    operation: str,
) -> dict[str, tuple[str, str]]:
    """실데이터 profile과 업무 타입 보호 규칙을 합쳐 operation 계약을 만든다."""

    fields = profile_operation.get("payload_fields") or profile_operation.get("fields")
    if not isinstance(fields, dict):
        raise ValueError(f"profile has no payload fields: {dataset}/{operation}")

    contract: dict[str, tuple[str, str]] = {}
    for raw_name, stats in fields.items():
        inferred = infer_dtype(stats)
        contract[raw_name] = (
            canonical_name(dataset, operation, raw_name),
            canonical_dtype(dataset, operation, raw_name, inferred),
        )
    return contract


def normalize_payload(
    payload: dict[str, Any],
    contract: dict[str, tuple[str, str]],
) -> tuple[dict[str, Any], list[str]]:
    """payload를 정규화하고 실제 값이 변환되지 못한 필드를 별도 기록한다."""

    output: dict[str, Any] = {}
    errors: list[str] = []
    for raw_name, (output_name, dtype) in contract.items():
        raw_value = payload.get(raw_name)
        converted = _convert(raw_value, dtype)
        if raw_value not in (None, "") and converted is None and dtype != "string":
            errors.append(raw_name)
        output[output_name] = converted
    return output, errors


normalize_record = normalize_payload
