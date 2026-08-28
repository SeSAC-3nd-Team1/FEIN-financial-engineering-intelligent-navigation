"""Strict contracts for MBGCoordinator weight modification gate (fix1)."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WeightProposalFix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stock_code: str = Field(pattern=r"^[0-9A-Z]{6,12}$")
    baseline_weight: Decimal = Field(ge=0, le=1)
    proposed_weight: Decimal = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=500)


class MBGWeightResponseFix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    proposals: list[WeightProposalFix]
    confidence: Decimal = Field(ge=0, le=1)
    risk_flags: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1, max_length=1000)


class WeightGateConfigFix(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    cash_buffer: Decimal = Field(default=Decimal("0.05"), ge=0, lt=1)
    max_symbol_adjustment: Decimal = Field(default=Decimal("0.10"), ge=0, le=1)
    minimum_agent_confidence: Decimal = Field(default=Decimal("0.60"), ge=0, le=1)
    max_signal_age_seconds: int = Field(default=3600, ge=1, le=86400)


class WeightGateResultFix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_weights: dict[str, Decimal]
    approved_weights: dict[str, Decimal]
    agent_applied: bool
    reasons: list[str]
    coordinator_request_id: str | None = None
    evaluated_at: datetime

    @model_validator(mode="after")
    def validate_approved_total(self):
        if sum(self.approved_weights.values(), Decimal("0")) > Decimal("1"):
            raise ValueError("approved weights exceed 1")
        return self
