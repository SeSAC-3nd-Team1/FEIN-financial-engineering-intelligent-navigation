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
    candidates = [text]
    candidates.extend(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL))
    decoder = json.JSONDecoder()
    for candidate in candidates:
        stripped = candidate.strip()
        try:
            value = json.loads(stripped)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            for index, character in enumerate(stripped):
                if character != "{":
                    continue
                try:
                    value, _ = decoder.raw_decode(stripped[index:])
                    if isinstance(value, dict):
                        return value
                except json.JSONDecodeError:
                    continue
    raise ValueError("response does not contain a valid JSON object")
