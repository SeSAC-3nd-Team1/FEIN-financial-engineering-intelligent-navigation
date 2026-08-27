import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ReportStatus(StrEnum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    TOOL_ERROR = "TOOL_ERROR"


class Source(BaseModel):
    title: str
    publisher: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    data_as_of: datetime | None = None
    primary_source: bool = False


class AgentRequest(BaseModel):
    request_id: str
    role: str
    user_query: str
    ticker: str | None = None
    company_name: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class CoordinatorPlan(BaseModel):
    request_id: str
    ticker: str | None = None
    company_name: str | None = None
    selected_roles: list[str]
    tasks: dict[str, str]


class AgentReport(BaseModel):
    agent: str
    request_id: str | None = None
    ticker: str | None = None
    company_name: str | None = None
    as_of: datetime | None = None
    data_freshness: str = "UNKNOWN"
    status: ReportStatus
    summary: str = ""
    facts: list[Any] = Field(default_factory=list)
    estimates: list[Any] = Field(default_factory=list)
    assumptions: list[Any] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class SpecialistOutcome(BaseModel):
    role: str
    report: AgentReport | None = None
    error_code: str | None = None
    error_message: str | None = None


class OrchestrationResult(BaseModel):
    request_id: str
    plan: CoordinatorPlan
    specialists: list[SpecialistOutcome]
    final_report: AgentReport
    trade_blocked: bool = True
    block_reasons: list[str] = Field(default_factory=list)


def extract_json_object(text: str) -> dict[str, Any]:
    fenced_payloads = re.findall(
        r"```[ \t]*(?:json[ \t]*)?(?:\r?\n)(?P<payload>.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fenced_payloads:
        if len(fenced_payloads) > 1:
            raise ValueError("response contains multiple fenced JSON payloads")
        try:
            value = json.loads(fenced_payloads[0].strip())
        except json.JSONDecodeError as error:
            raise ValueError("fenced JSON payload is invalid") from error
        if isinstance(value, dict):
            return value
        raise ValueError("fenced JSON payload must be a JSON object")

    if re.search(r"```[ \t]*(?:json[ \t]*)?(?:\r?\n|$)", text, flags=re.IGNORECASE):
        raise ValueError("response contains an incomplete fenced JSON payload")

    decoder = json.JSONDecoder()
    spans: list[tuple[int, int, str]] = []
    open_delimiters: list[tuple[str, int]] = []
    in_string = False
    escaped = False
    for index, character in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            open_delimiters.append((character, index))
        elif character in "]}" and open_delimiters:
            opening, start = open_delimiters[-1]
            if (opening, character) in (("[", "]"), ("{", "}")):
                open_delimiters.pop()
                spans.append((start, index + 1, opening))

    valid_contexts: list[tuple[int, int, str]] = []
    valid_objects: list[tuple[int, int, dict[str, Any]]] = []
    for start, end, opening in spans:
        try:
            value, decoded_end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if decoded_end != end - start:
            continue
        if opening == "{" and isinstance(value, dict):
            valid_objects.append((start, end, value))
            valid_contexts.append((start, end, opening))
        elif opening == "[" and isinstance(value, list):
            valid_contexts.append((start, end, opening))

    for start, end, _ in valid_objects:
        if any(unclosed_start < start for _, unclosed_start in open_delimiters):
            raise ValueError("response contains an incomplete JSON context")
        if any(
            outer_start < start
            and outer_end >= end
            and not any(
                outer_start == valid_start
                and outer_end == valid_end
                and opening == valid_opening
                for valid_start, valid_end, valid_opening in valid_contexts
            )
            for outer_start, outer_end, opening in spans
        ):
            raise ValueError("response contains an invalid enclosing JSON context")

    objects = [
        value
        for start, end, value in valid_objects
        if not any(
            outer_start < start
            and outer_end >= end
            for outer_start, outer_end, _ in valid_objects
        )
    ]
    if len(objects) == 1:
        return objects[0]
    if len(objects) > 1:
        raise ValueError("response contains multiple JSON objects")
    raise ValueError("response does not contain a valid JSON object")
