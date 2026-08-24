"""REST request/response schema."""

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.config import settings


class AgreementRequest(BaseModel):
    term_code: str = Field(min_length=1, max_length=30)
    version: str = Field(min_length=1, max_length=20)
    agreed: bool


class SignupRequest(BaseModel):
    user_id: str = Field(pattern=r"^[a-z0-9]{6,16}$")
    password: str = Field(
        min_length=8,
        max_length=72,
        pattern=r"^[A-Za-z\d@$!%*#?&]+$",
    )
    name: str = Field(min_length=1, max_length=30)
    birthdate: str = Field(pattern=r"^[0-9]{6}$")
    phone_number: str = Field(pattern=r"^0[0-9]{9,10}$")
    email: EmailStr
    phone_verified: bool
    email_verified: bool
    agreements: list[AgreementRequest] = Field(default_factory=list)

    @field_validator("password")
    @classmethod
    def validate_password_composition(cls, value: str) -> str:
        if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError("password must include letters and digits")
        if not any(char in "@$!%*#?&" for char in value):
            raise ValueError("password must include a special character")
        return value


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


class TermResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    term_code: str
    version: str
    title: str
    is_required: bool


class InvestmentTermResponse(TermResponse):
    content_reference: str | None = None


class InvestmentOnboardingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1, max_length=30)
    investment_amount: Decimal = Field(gt=0, le=100_000_000)
    operation_mode: Literal["AUTO", "SEMI_AUTO"]


class InvestmentAgreementSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agreements: list[AgreementRequest] = Field(min_length=1, max_length=10)


class InvestmentAccountPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_name: str = Field(default="나의 가상 투자계좌", min_length=1, max_length=100)


class InvestmentOnboardingResponse(BaseModel):
    id: UUID
    strategy_id: str
    investment_amount: Decimal
    operation_mode: Literal["AUTO", "SEMI_AUTO"]
    status: Literal["TERMS_PENDING", "ACCOUNT_PENDING", "READY", "COMPLETED"]
    account_id: UUID | None
    terms_completed: bool
    account_exists: bool
    next_step: Literal["TERMS", "ACCOUNT", "CONFIRM", "PORTFOLIO"]
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


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


class InvestmentAccountPrepareResponse(BaseModel):
    account: AccountResponse
    created: bool
    onboarding: InvestmentOnboardingResponse


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    risk_level: str
    rebalance_cycle: str


class BacktestRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    strategy_id: str = Field(alias="strategyId", min_length=1, max_length=30)
    period_id: str = Field(alias="periodId", min_length=1, max_length=50)
    period_label: str = Field(alias="periodLabel", min_length=1, max_length=100)
    period_description: str = Field(alias="periodDescription", max_length=500)
    start_date: date = Field(alias="startDate")
    end_date: date = Field(alias="endDate")

    @model_validator(mode="after")
    def validate_period(self) -> "BacktestRunRequest":
        if self.start_date >= self.end_date:
            raise ValueError("startDate must be before endDate")
        if (self.end_date - self.start_date).days > 3660:
            raise ValueError("backtest period must not exceed 10 years")
        return self


class BacktestPeriodResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    label: str
    start_date: date = Field(alias="startDate")
    end_date: date = Field(alias="endDate")
    description: str


class BacktestAvailableRangeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    min_date: date = Field(alias="minDate")
    max_date: date = Field(alias="maxDate")


class BacktestSeriesPointResponse(BaseModel):
    t: date
    strategy: float
    benchmark: float


class BacktestMetricsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cumulative_return: float = Field(alias="cumulativeReturn")
    cagr: float
    mdd: float
    volatility: float
    sharpe: float | None


class BacktestBenchmarkMetricsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cumulative_return: float = Field(alias="cumulativeReturn")
    mdd: float


class BacktestRunResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    strategy_id: str = Field(alias="strategyId")
    strategy_name: str = Field(alias="strategyName")
    period: BacktestPeriodResponse
    series: list[BacktestSeriesPointResponse]
    metrics: BacktestMetricsResponse
    benchmark_name: str = Field(alias="benchmarkName")
    benchmark_metrics: BacktestBenchmarkMetricsResponse = Field(alias="benchmarkMetrics")


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
    previous_close: Decimal | None = None
    change_amount: Decimal | None = None
    change_rate: Decimal | None = None
    volume: int | None = None
    source: str
    as_of: datetime


class StockSummaryResponse(BaseModel):
    stock_code: str
    stock_name: str
    market: str
    sector: str | None
    listing_date: date | None
    listed_shares: int | None
    security_type: str | None
    description: str | None
    price: Decimal | None
    previous_close: Decimal | None
    change_amount: Decimal | None
    change_rate: Decimal | None
    volume: int | None
    market_cap: Decimal | None
    per: Decimal | None
    pbr: Decimal | None
    roe: Decimal | None
    dividend_yield: Decimal | None
    financial_year: str | None
    as_of: datetime | None
    sources: dict[str, str | None]


class StockChartItemResponse(BaseModel):
    date: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class StockChartResponse(BaseModel):
    stock_code: str
    period: Literal["1D", "1W", "3M", "6M", "1Y", "5Y"]
    source: str
    as_of: datetime
    items: list[StockChartItemResponse]


class MinuteCandleResponse(BaseModel):
    started_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    is_closed: bool


class MinuteCandleListResponse(BaseModel):
    stock_code: str
    interval: Literal["1m"] = "1m"
    items: list[MinuteCandleResponse]
    source: str
    as_of: datetime


class RealtimeSubscriptionRequest(BaseModel):
    action: Literal["subscribe", "unsubscribe"]
    stock_codes: list[str] = Field(min_length=1)
    token: str | None = Field(default=None, min_length=1, max_length=4096)

    @field_validator("stock_codes")
    @classmethod
    def validate_stock_codes(cls, value: list[str]) -> list[str]:
        if len(value) > settings.realtime_max_symbols_per_client:
            raise ValueError("too many stock codes")
        normalized = list(dict.fromkeys(value))
        if any(not re.fullmatch(r"^[0-9A-Z]{6,12}$", code) for code in normalized):
            raise ValueError("invalid stock code")
        return normalized


class RealtimeStatusResponse(BaseModel):
    configured: bool
    connected: bool
    subscribed_symbols: int
    downstream_clients: int
    last_received_at: datetime | None
    last_error: str | None


class PositionResponse(BaseModel):
    stock_code: str
    stock_name: str | None
    sector: str | None
    quantity: int
    average_price: Decimal
    current_price: Decimal
    previous_close: Decimal | None
    change_rate: Decimal | None
    purchase_amount: Decimal
    evaluation_amount: Decimal
    unrealized_profit: Decimal
    return_rate: Decimal
    realized_profit: Decimal
    weight: Decimal
    today_profit: Decimal | None
    price_source: str
    price_as_of: datetime


class PortfolioContributionResponse(BaseModel):
    stock_code: str
    stock_name: str | None
    amount: Decimal
    share_rate: Decimal | None


class RebalancingProposalResponse(BaseModel):
    stock_code: str
    stock_name: str | None
    current_weight: Decimal
    target_weight: Decimal
    weight_diff: Decimal
    action: Literal["BUY", "SELL"]
    recommended_amount: Decimal


class PortfolioResponse(BaseModel):
    account_id: UUID
    cash_balance: Decimal
    total_purchase_amount: Decimal
    total_evaluation_amount: Decimal
    total_assets: Decimal
    unrealized_profit: Decimal
    realized_profit: Decimal
    return_rate: Decimal
    today_profit: Decimal | None
    top_contributor: PortfolioContributionResponse | None
    contributions: list[PortfolioContributionResponse]
    strategy_targets_available: bool
    rebalancing_proposals: list[RebalancingProposalResponse]
    positions: list[PositionResponse]


class PortfolioHistoryPointResponse(BaseModel):
    date: date
    total_assets: Decimal
    portfolio_return_rate: Decimal
    benchmark_return_rate: Decimal | None


class PortfolioHistoryResponse(BaseModel):
    account_id: UUID
    period: Literal["1M", "3M", "1Y", "ALL"]
    benchmark_name: str
    items: list[PortfolioHistoryPointResponse]


class StockEvaluationAxisResponse(BaseModel):
    key: Literal["stability", "financial_health", "growth", "defense", "diversification"]
    label: str
    score: int | None = Field(ge=0, le=100)
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    basis: str


class StockEvaluationResponse(BaseModel):
    account_id: UUID
    stock_code: str
    stock_name: str | None
    feature_version: Literal["stock-feature-v1"] = "stock-feature-v1"
    as_of: date | None
    target_weight: Decimal | None
    role_summary: str | None
    axes: list[StockEvaluationAxisResponse]
    sources: list[Literal["KRX", "OpenDART", "Portfolio"]]


class RebalancingDecisionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    stock_code: str = Field(pattern=r"^[0-9A-Z]{6,12}$")
    decision: Literal["ACCEPTED", "HELD"]
    idempotency_key: str = Field(min_length=1, max_length=100)


class RebalancingDecisionResponse(BaseModel):
    id: UUID
    account_id: UUID
    strategy_id: str | None
    stock_code: str
    stock_name: str | None
    action: Literal["BUY", "SELL"]
    current_weight: Decimal
    target_weight: Decimal
    weight_diff: Decimal
    recommended_amount: Decimal
    decision: Literal["ACCEPTED", "HELD"]
    baseline_snapshot_date: date | None
    actual_portfolio_return_rate: Decimal | None
    outcome_as_of: date | None
    created_at: datetime


class RebalancingDecisionHistoryResponse(BaseModel):
    account_id: UUID
    period_label: Literal["최근 6개월"] = "최근 6개월"
    proposed: int
    accepted: int
    held: int
    items: list[RebalancingDecisionResponse]


class ErrorResponse(BaseModel):
    code: str
    message: str


class InvestorAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=50)
    option_id: str = Field(min_length=1, max_length=50)


class InvestorProfileAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questionnaire_version: str = Field(min_length=1, max_length=20)
    answers: list[InvestorAnswerRequest] = Field(min_length=1, max_length=20)


class InvestorTraitsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stability: int = Field(ge=1, le=5)
    return_seeking: int = Field(ge=1, le=5)
    horizon: int = Field(ge=1, le=5)


class InvestorProfileAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_type: Literal[
        "안정추구형",
        "안정투자형",
        "중립투자형",
        "성장추구형",
        "공격투자형",
    ]
    tendency_line: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)
    traits: InvestorTraitsResponse
    analysis_summary: list[str] = Field(min_length=1, max_length=5)


class InvestorProfileResponse(InvestorProfileAnalysisResult):
    assessment_id: UUID
    questionnaire_version: str
    analysis_version: Literal["v1"] = "v1"
    model_version: str
    created_at: datetime


class StrategyRecommendationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: UUID


class StrategyRecommendationAnalysisItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1, max_length=30)
    rank: int = Field(ge=1, le=3)
    score: float = Field(ge=0, le=1)
    match_level: Literal["BEST", "GOOD", "CAUTION"]
    reason: str = Field(min_length=1, max_length=500)
    caution: str = Field(min_length=1, max_length=500)


class StrategyRecommendationAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendations: list[StrategyRecommendationAnalysisItem] = Field(min_length=1, max_length=3)


class StrategyRecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: UUID
    assessment_id: UUID
    primary: StrategyRecommendationAnalysisItem
    alternatives: list[StrategyRecommendationAnalysisItem]
    model_version: str
    dataset_version: str
    recommendation_version: Literal["v1"] = "v1"
    created_at: datetime


class NewsArticleResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    title: str
    summary: str
    thumbnail: str | None = None
    publisher: str
    published_at: datetime = Field(alias="publishedAt")
    link: str


class NewsListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    items: list[NewsArticleResponse]
    total_count: int = Field(alias="totalCount", ge=0)
    updated_at: datetime = Field(alias="updatedAt")


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    corp_code: str
    stock_code: str | None
    corp_name: str
    corp_name_eng: str | None
    stock_name: str | None
    market: str | None
    ceo_name: str | None
    jurir_no: str | None
    bizr_no: str | None
    address: str | None
    homepage_url: str | None
    ir_url: str | None
    phone_number: str | None
    industry_code: str | None
    established_date: date | None
    accounting_month: str | None
    source: Literal["OpenDART"] = "OpenDART"


class CompanyFinancialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    business_year: str
    report_code: str
    quarter: str
    fs_div: str
    revenue: Decimal | None
    operating_income: Decimal | None
    net_income: Decimal | None
    total_assets: Decimal | None
    total_liabilities: Decimal | None
    total_equity: Decimal | None
    operating_cash_flow: Decimal | None
    investing_cash_flow: Decimal | None
    financing_cash_flow: Decimal | None


class CompanyFinancialListResponse(BaseModel):
    stock_code: str
    items: list[CompanyFinancialResponse]
    source: Literal["OpenDART"] = "OpenDART"


class CompanyDisclosureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    receipt_no: str
    corp_code: str
    stock_code: str | None
    corp_name: str
    report_name: str
    filer_name: str | None
    receipt_date: date
    remarks: str | None


class CompanyDisclosureListResponse(BaseModel):
    stock_code: str
    items: list[CompanyDisclosureResponse]
    source: Literal["OpenDART"] = "OpenDART"
