"""Stable contracts between Algorithm v2.3, FINCON-style agents and execution."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AlgorithmSignal(BaseModel):
    """Normalized output adapter for Algorithm(ver2.3).

    The algorithm remains outside the web process.  Its latest target weights and
    stop metadata cross this small contract, avoiding imports from experiment files.
    """

    model_config = ConfigDict(extra="forbid")
    algorithm_version: Literal["2.3"] = "2.3"
    generated_at: datetime
    target_weights: dict[str, Decimal]
    stop_prices: dict[str, Decimal] = Field(default_factory=dict)
    confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)

    @model_validator(mode="after")
    def validate_weights(self):
        if any(weight < 0 or weight > 1 for weight in self.target_weights.values()):
            raise ValueError("target weights must be in [0, 1]")
        if sum(self.target_weights.values(), Decimal("0")) > Decimal("1"):
            raise ValueError("target weights cannot exceed 1")
        if any(price <= 0 for price in self.stop_prices.values()):
            raise ValueError("stop prices must be positive")
        return self


class CoordinatorAdvice(BaseModel):
    """Optional future bridge from MBGCoordinator/FINCON manager synthesis."""

    model_config = ConfigDict(extra="forbid")
    request_id: str
    confidence: Decimal = Field(ge=0, le=1)
    blocked_symbols: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    summary: str = ""


class EngineRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID
    signal: AlgorithmSignal
    coordinator_advice: CoordinatorAdvice | None = None
    execute: bool = False
    max_turnover: Decimal = Field(default=Decimal("0.30"), ge=0, le=1)
    min_order_amount: Decimal = Field(default=Decimal("1000"), ge=1)
    cash_buffer: Decimal = Field(default=Decimal("0.05"), ge=0, lt=1)


class EngineOrder(BaseModel):
    stock_code: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(gt=0)
    reference_price: Decimal = Field(gt=0)
    amount: Decimal = Field(gt=0)
    reason: Literal["STOP_LOSS", "REBALANCE"]
    target_weight: Decimal = Field(ge=0, le=1)
    idempotency_key: str
    status: Literal["PLANNED", "FILLED", "SKIPPED"] = "PLANNED"


class EngineRunResponse(BaseModel):
    engine_version: Literal["fincon-ver23-v1"] = "fincon-ver23-v1"
    account_id: UUID
    generated_at: datetime
    execution_mode: Literal["DRY_RUN", "PAPER"]
    orders: list[EngineOrder]
    blocked_reasons: list[str]
    coordinator_request_id: str | None = None
