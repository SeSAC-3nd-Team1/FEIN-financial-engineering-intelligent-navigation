"""REST request/response schema."""

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.core.config import settings

OperationMode = Literal["AUTO", "SEMI_AUTO"]


class AgreementRequest(BaseModel):
    term_code: str = Field(min_length=1, max_length=30)
    version: str = Field(min_length=1, max_length=20)
    agreed: bool


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    email_verification_token: str = Field(min_length=32, max_length=128)
    agreements: list[AgreementRequest] = Field(default_factory=list)

    @field_validator("password")
    @classmethod
    def validate_password_composition(cls, value: str) -> str:
        if not any(char.isalpha() for char in value) or not any(
            char.isdigit() for char in value
        ):
            raise ValueError("password must include letters and digits")
        if not any(char in "@$!%*#?&" for char in value):
            raise ValueError("password must include a special character")
        return value


class EmailVerificationSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class EmailVerificationSendResponse(BaseModel):
    verification_id: UUID
    expires_in_seconds: int
    resend_after_seconds: int


class EmailVerificationVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_id: UUID
    code: str = Field(pattern=r"^[0-9]{6}$")


class EmailVerificationVerifyResponse(BaseModel):
    verification_token: str
    expires_in_seconds: int


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
    active_operation_mode: OperationMode | None = None
    operation_mode_changed_at: datetime | None = None


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
    operation_mode: OperationMode


class InvestmentAgreementSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agreements: list[AgreementRequest] = Field(min_length=1, max_length=10)


class InvestmentAccountPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_name: str = Field(
        default="나의 가상 투자계좌", min_length=1, max_length=100
    )


class InvestmentDepositRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, le=100_000_000)
    idempotency_key: str = Field(min_length=8, max_length=100)


class InvestmentOnboardingResponse(BaseModel):
    id: UUID
    strategy_id: str
    investment_amount: Decimal
    operation_mode: OperationMode
    status: Literal[
        "TERMS_PENDING", "ACCOUNT_PENDING", "DEPOSIT_PENDING", "READY", "COMPLETED"
    ]
    account_id: UUID | None
    terms_completed: bool
    account_exists: bool
    next_step: Literal["TERMS", "ACCOUNT", "DEPOSIT", "CONFIRM", "PORTFOLIO"]
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AccountCreateRequest(BaseModel):
    account_name: str = Field(
        default="나의 가상 투자계좌", min_length=1, max_length=100
    )
    operation_mode: OperationMode = "SEMI_AUTO"


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    account_name: str
    operation_mode: OperationMode
    initial_cash: Decimal
    cash_balance: Decimal
    invested_principal: Decimal = Decimal("0")
    status: str
    selected_strategy_id: str | None
    created_at: datetime

    @field_validator("invested_principal", mode="before")
    @classmethod
    def normalize_legacy_principal(cls, value):
        # 마이그레이션 전 객체를 직접 만드는 단위 테스트와 순차 배포 중 응답도 0원으로 수렴시킨다.
        return Decimal("0") if value is None else value


class OperationModeSwitchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_mode: OperationMode


class OperationModeChangeNoticeResponse(BaseModel):
    code: Literal["OPERATION_MODE_CHANGED", "OPERATION_MODE_UNCHANGED"]
    title: str
    message: str


class OperationModeSwitchResponse(BaseModel):
    previous_operation_mode: OperationMode | None
    operation_mode: OperationMode
    changed: bool
    changed_at: datetime | None
    account: AccountResponse
    notice: OperationModeChangeNoticeResponse


class InvestmentAccountPrepareResponse(BaseModel):
    account: AccountResponse
    created: bool
    required_deposit_amount: Decimal
    onboarding: InvestmentOnboardingResponse


class InvestmentDepositResponse(BaseModel):
    deposit_id: UUID
    amount: Decimal
    balance_after: Decimal
    required_deposit_amount: Decimal
    onboarding: InvestmentOnboardingResponse


class FundOperationRequest(BaseModel):
    """내부 가상 자산만 변경하는 멱등한 추가투자·출금 요청이다."""

    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(ge=1, le=100_000_000, decimal_places=2)
    idempotency_key: str = Field(min_length=8, max_length=100)


class FundTradeResponse(BaseModel):
    order_id: UUID
    stock_code: str
    side: Literal["BUY", "SELL"]
    applied_weight: Decimal
    quantity: Decimal
    execution_price: Decimal
    transaction_amount: Decimal


class FundSummaryResponse(BaseModel):
    account_id: UUID
    settlement_mode: Literal["VIRTUAL"] = "VIRTUAL"
    invested_principal: Decimal
    cash_balance: Decimal
    position_evaluation_amount: Decimal
    total_assets: Decimal
    valuation_profit: Decimal
    return_rate: Decimal
    withdrawable_amount: Decimal
    valuation_as_of: datetime | None


class FundOperationResponse(BaseModel):
    operation_id: UUID
    type: Literal["ADDITIONAL_INVESTMENT", "WITHDRAWAL"]
    status: Literal["COMPLETED"]
    settlement_mode: Literal["VIRTUAL"] = "VIRTUAL"
    requested_amount: Decimal
    executed_amount: Decimal
    principal_before: Decimal
    principal_after: Decimal
    portfolio: FundSummaryResponse
    trades: list[FundTradeResponse]


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    risk_level: str
    rebalance_cycle: str
    product_group: Literal["MUL", "BANG"]
    availability_status: Literal["AVAILABLE", "TESTING"]
    engine_key: str
    display_order: int


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
    benchmark_metrics: BacktestBenchmarkMetricsResponse = Field(
        alias="benchmarkMetrics"
    )


class StrategySelectRequest(BaseModel):
    strategy_id: str


class OrderCreateRequest(BaseModel):
    account_id: UUID
    stock_code: str = Field(pattern=r"^[0-9A-Z]{6,12}$")
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET"] = "MARKET"
    quantity: Decimal = Field(gt=0, le=1_000_000, decimal_places=8)
    idempotency_key: str = Field(min_length=8, max_length=100)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    account_id: UUID
    stock_code: str
    side: str
    order_type: str
    quantity: Decimal
    status: str
    requested_price: Decimal | None
    requested_at: datetime


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_id: UUID
    stock_code: str
    side: str
    quantity: Decimal
    execution_price: Decimal
    executed_at: datetime


class PortfolioTransactionResponse(BaseModel):
    id: int
    order_id: UUID
    stock_code: str
    stock_name: str | None
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    execution_price: Decimal
    transaction_amount: Decimal
    executed_at: datetime


class PortfolioTransactionListResponse(BaseModel):
    account_id: UUID
    items: list[PortfolioTransactionResponse]
    next_cursor: str | None
    has_more: bool


class PortfolioActivityResponse(BaseModel):
    id: int
    type: Literal["BUY", "SELL", "ADDITIONAL_INVESTMENT", "WITHDRAWAL"]
    cash_amount: Decimal
    transaction_amount: Decimal
    balance_after: Decimal
    reference_id: str
    order_id: UUID | None = None
    stock_code: str | None = None
    stock_name: str | None = None
    quantity: Decimal | None = None
    execution_price: Decimal | None = None
    occurred_at: datetime


class PortfolioActivityListResponse(BaseModel):
    account_id: UUID
    settlement_mode: Literal["VIRTUAL"] = "VIRTUAL"
    items: list[PortfolioActivityResponse]
    next_cursor: str | None
    has_more: bool


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
    quantity: Decimal
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
    priority: int | None = Field(default=None, ge=1, le=5)
    reason: str | None = Field(default=None, max_length=500)
    why_now: str | None = Field(default=None, max_length=500)
    source: Literal["RULE", "AI"] = "RULE"


class RebalancingInsightResponse(BaseModel):
    status: Literal["AVAILABLE", "NOT_NEEDED", "UNAVAILABLE"]
    summary: str | None
    model_version: str | None
    generated_at: datetime | None


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
    invested_principal: Decimal = Decimal("0")
    valuation_profit: Decimal = Decimal("0")
    withdrawable_amount: Decimal = Decimal("0")
    settlement_mode: Literal["VIRTUAL"] = "VIRTUAL"


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


class PortfolioComparisonAccountResponse(BaseModel):
    account_id: UUID
    account_name: str
    operation_mode: OperationMode
    strategy_id: str | None
    baseline_assets: Decimal | None
    current_assets: Decimal | None
    return_rate: Decimal | None


class PortfolioComparisonAccountsResponse(BaseModel):
    ai_auto: PortfolioComparisonAccountResponse
    my_investment: PortfolioComparisonAccountResponse


class PortfolioComparisonMetricsResponse(BaseModel):
    return_rate_gap: Decimal
    asset_gap: Decimal
    leader: Literal["AI_AUTO", "MY_INVESTMENT", "TIE"]


class PortfolioComparisonPointResponse(BaseModel):
    date: date
    ai_auto_return_rate: Decimal
    my_investment_return_rate: Decimal
    return_rate_gap: Decimal


class PortfolioComparisonAIAnalysisResponse(BaseModel):
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    headline: str | None = None
    summary: str
    key_points: list[str] = Field(default_factory=list)
    caution: str | None = None
    model_version: str | None = None
    generated_at: datetime | None = None


class PortfolioComparisonResponse(BaseModel):
    comparison_status: Literal["AVAILABLE", "INSUFFICIENT_DATA"]
    calculation_version: Literal["portfolio-comparison-v1"] = "portfolio-comparison-v1"
    return_calculation: Literal["CASH_FLOW_ADJUSTED_TWR"] = "CASH_FLOW_ADJUSTED_TWR"
    period: Literal["1M", "3M", "1Y", "ALL"]
    baseline_date: date | None
    as_of: date | None
    observation_count: int = Field(ge=0)
    accounts: PortfolioComparisonAccountsResponse
    metrics: PortfolioComparisonMetricsResponse | None
    series: list[PortfolioComparisonPointResponse]
    ai_analysis: PortfolioComparisonAIAnalysisResponse


class PortfolioHomeAccountResponse(BaseModel):
    id: UUID
    account_name: str
    operation_mode: OperationMode
    status: str
    selected_strategy_id: str | None


class PortfolioHomeSummaryResponse(BaseModel):
    cash_balance: Decimal
    total_purchase_amount: Decimal
    total_evaluation_amount: Decimal
    total_assets: Decimal
    unrealized_profit: Decimal
    realized_profit: Decimal
    return_rate: Decimal
    today_profit: Decimal | None
    top_contributor: PortfolioContributionResponse | None
    invested_principal: Decimal = Decimal("0")
    valuation_profit: Decimal = Decimal("0")
    withdrawable_amount: Decimal = Decimal("0")


class PortfolioAllocationResponse(BaseModel):
    type: Literal["STOCK", "CASH"]
    stock_code: str | None
    name: str
    amount: Decimal
    weight: Decimal


class PortfolioHomeResponse(BaseModel):
    account: PortfolioHomeAccountResponse
    summary: PortfolioHomeSummaryResponse
    trend: PortfolioHistoryResponse
    allocations: list[PortfolioAllocationResponse]
    positions: list[PositionResponse]
    contributions: list[PortfolioContributionResponse]
    strategy_targets_available: bool
    rebalancing_insight: RebalancingInsightResponse
    rebalancing_proposals: list[RebalancingProposalResponse]
    valuation_as_of: datetime | None
    price_sources: list[str]


class StockEvaluationAxisResponse(BaseModel):
    key: Literal[
        "stability", "financial_health", "growth", "defense", "diversification"
    ]
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

    recommendations: list[StrategyRecommendationAnalysisItem] = Field(
        min_length=1, max_length=3
    )


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


class ModelRecommendationItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^[0-9A-Z]{6,12}$")
    stock_name: str | None = Field(default=None, max_length=200)
    score: float
    rank: int = Field(ge=1)
    target_weight: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=500)


class ModelRecommendationSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date
    generated_at: datetime
    model_version: str = Field(min_length=1, max_length=100)
    data_version: str = Field(min_length=1, max_length=100)
    status: Literal["ready", "unavailable"]
    market_regime: Literal["risk_on", "neutral", "risk_off"]
    source: Literal["generated", "fallback"]
    is_stale: bool
    recommendations: list[ModelRecommendationItemResponse] = Field(max_length=20)


class ModelRecommendationApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID


class ModelRecommendationApplyResponse(BaseModel):
    account_id: UUID
    strategy_id: Literal["low", "momentum"]
    as_of: date
    target_count: int = Field(ge=1)
    orders_created: int = Field(ge=0)
    status: Literal["APPLIED", "PROPOSAL_ONLY", "ALREADY_APPLIED"]


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
