"""REST request/response schema."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AgreementRequest(BaseModel):
    term_code: str = Field(min_length=1, max_length=30)
    version: str = Field(min_length=1, max_length=20)
    agreed: bool


class SignupRequest(BaseModel):
    user_id: str = Field(pattern=r"^[a-z0-9]{6,16}$")
    password: str = Field(min_length=8, max_length=72)
    name: str = Field(min_length=1, max_length=30)
    birthdate: str = Field(pattern=r"^[0-9]{6}$")
    phone_number: str = Field(pattern=r"^0[0-9]{9,10}$")
    email: EmailStr
    phone_verified: bool
    email_verified: bool
    agreements: list[AgreementRequest] = Field(default_factory=list)


class LoginRequest(BaseModel):
    user_id: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: str
    name: str
    email: str
    account_status: str


class AccountCreateRequest(BaseModel):
    account_name: str = Field(default="나의 가상 투자계좌", min_length=1, max_length=100)


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    account_name: str
    initial_cash: Decimal
    cash_balance: Decimal
    status: str
    selected_strategy_id: str | None
    created_at: datetime


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    risk_level: str
    rebalance_cycle: str


class StrategySelectRequest(BaseModel):
    strategy_id: str


class OrderCreateRequest(BaseModel):
    account_id: UUID
    stock_code: str = Field(pattern=r"^[0-9A-Z]{6,12}$")
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET"] = "MARKET"
    quantity: int = Field(gt=0, le=1_000_000)
    idempotency_key: str = Field(min_length=8, max_length=100)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    account_id: UUID
    stock_code: str
    side: str
    order_type: str
    quantity: int
    status: str
    requested_price: Decimal | None
    requested_at: datetime


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_id: UUID
    stock_code: str
    side: str
    quantity: int
    execution_price: Decimal
    executed_at: datetime


class PriceResponse(BaseModel):
    stock_code: str
    price: Decimal
    source: str
    as_of: datetime


class PositionResponse(BaseModel):
    stock_code: str
    quantity: int
    average_price: Decimal
    current_price: Decimal
    purchase_amount: Decimal
    evaluation_amount: Decimal
    unrealized_profit: Decimal
    return_rate: Decimal
    realized_profit: Decimal


class PortfolioResponse(BaseModel):
    account_id: UUID
    cash_balance: Decimal
    total_purchase_amount: Decimal
    total_evaluation_amount: Decimal
    total_assets: Decimal
    unrealized_profit: Decimal
    realized_profit: Decimal
    return_rate: Decimal
    positions: list[PositionResponse]


class ErrorResponse(BaseModel):
    code: str
    message: str
