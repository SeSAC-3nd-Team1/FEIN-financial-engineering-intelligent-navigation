"""Profile contract를 이용해 Raw payload를 표준 컬럼과 Python scalar로 변환한다."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from processing.contracts import canonical_name
from processing.profile_contract import infer_dtype

def _convert(value: Any, dtype: str) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    if dtype == "date":
        return datetime.strptime(text, "%Y%m%d").date()
    if dtype == "integer":
        try: return int(text.replace(",", ""))
        except ValueError: return None
    if dtype == "number":
        try: return float(Decimal(text.replace(",", "")))
        except InvalidOperation: return None
    return text

def build_operation_contract(profile_operation: dict[str, Any], dataset: str, operation: str) -> dict[str, tuple[str,str]]:
    fields = profile_operation.get("payload_fields") or profile_operation.get("fields")
    if not isinstance(fields, dict):
        raise ValueError(f"profile has no payload fields: {dataset}/{operation}")
    return {raw:(canonical_name(dataset,operation,raw),infer_dtype(stats)) for raw,stats in fields.items()}

def normalize_payload(payload: dict[str, Any], contract: dict[str, tuple[str,str]]) -> tuple[dict[str,Any],list[str]]:
    output: dict[str,Any] = {}; errors: list[str] = []
    for raw_name,(output_name,dtype) in contract.items():
        raw_value = payload.get(raw_name); converted = _convert(raw_value,dtype)
        if raw_value not in (None,"") and converted is None and dtype != "string": errors.append(raw_name)
        output[output_name] = converted
    return output, errors
normalize_record = normalize_payload
