const API_BASE = "/api/v1";
export const TOKEN_STORAGE_KEY = "fein_access_token";

export interface AuthUser {
  id: number;
  user_id: string;
  name: string;
  email: string;
  account_status: string;
}

export interface SignupPayload {
  user_id: string;
  password: string;
  name: string;
  birthdate: string;
  phone_number: string;
  email: string;
  /** 이메일 인증 완료 시 /auth/email-verifications/verify가 발급하는 1회용 증명 토큰 */
  email_verification_token: string;
  agreements: { term_code: string; version: string; agreed: boolean }[];
}

export interface EmailVerificationSendResponse {
  verification_id: string;
  expires_in_seconds: number;
  resend_after_seconds: number;
}

export interface EmailVerificationVerifyResponse {
  verification_token: string;
  expires_in_seconds: number;
}

export interface SignupTerm {
  term_code: string;
  version: string;
  title: string;
  is_required: boolean;
}

/** Backend Decimal은 JSON 문자열로 직렬화된다. 금액 계산 시 Number로 명시 변환한다. */
export type DecimalString = string;

/** 백엔드가 구분하는 운용방식 — 프론트 전역의 `OperationMode`('auto'|'manual', data/fees.ts)와는
 *  표기가 달라 혼동하기 쉽다. 계좌 API 호출부에서만 쓰고, 그 밖의 화면은 계속 프론트 표기를 쓴다. */
export type AccountOperationMode = "AUTO" | "SEMI_AUTO";

export interface AccountResponse {
  id: string;
  account_name: string;
  operation_mode: AccountOperationMode;
  initial_cash: DecimalString;
  cash_balance: DecimalString;
  invested_principal?: DecimalString;
  status: string;
  selected_strategy_id: string | null;
  created_at: string;
}

export type CarGrade = "INEX" | "HIGHEND";

export interface CarGoalResponse {
  car_grade: CarGrade;
  goal_amount: DecimalString;
  current_amount: DecimalString;
  updated_at: string;
}

export interface CarGoalUpsertRequest {
  car_grade: CarGrade;
  goal_amount: number;
  // current_amount는 여기 없다 — 실제 투자 금액은 서버가 계좌를 조회해 계산한다.
  // 클라이언트가 보낸 값을 그대로 믿고 저장하면 요청을 조작해 실제 금액과 다른 값을
  // 저장할 수 있다(PR #257 리뷰).
}

export interface AccountCashDepositResponse {
  deposit_id: string;
  account: AccountResponse;
  amount: DecimalString;
  balance_after: DecimalString;
  status: "COMPLETED";
}

export interface FundOperationRequest {
  amount: number;
  idempotency_key: string;
}

export interface FundSummaryResponse {
  account_id: string;
  settlement_mode: "VIRTUAL";
  invested_principal: DecimalString;
  cash_balance: DecimalString;
  position_evaluation_amount: DecimalString;
  total_assets: DecimalString;
  valuation_profit: DecimalString;
  return_rate: DecimalString;
  withdrawable_amount: DecimalString;
  valuation_as_of: string | null;
}

export interface FundTradeResponse {
  order_id: string;
  stock_code: string;
  side: "BUY" | "SELL";
  applied_weight: DecimalString;
  quantity: DecimalString;
  execution_price: DecimalString;
  transaction_amount: DecimalString;
}

export interface FundOperationResponse {
  operation_id: string;
  type: "ADDITIONAL_INVESTMENT" | "WITHDRAWAL";
  status: "COMPLETED";
  settlement_mode: "VIRTUAL";
  requested_amount: DecimalString;
  executed_amount: DecimalString;
  principal_before: DecimalString;
  principal_after: DecimalString;
  portfolio: FundSummaryResponse;
  trades: FundTradeResponse[];
}

export interface InvestmentTermResponse extends SignupTerm {
  content_reference: string | null;
}

export type InvestmentOnboardingStatus =
  | "TERMS_PENDING"
  | "ACCOUNT_PENDING"
  | "DEPOSIT_PENDING"
  | "READY"
  | "COMPLETED";

export interface InvestmentOnboardingResponse {
  id: string;
  strategy_id: string;
  investment_amount: DecimalString;
  operation_mode: AccountOperationMode;
  status: InvestmentOnboardingStatus;
  account_id: string | null;
  terms_completed: boolean;
  account_exists: boolean;
  next_step: "TERMS" | "ACCOUNT" | "DEPOSIT" | "CONFIRM" | "PORTFOLIO";
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InvestmentAccountPrepareResponse {
  account: AccountResponse;
  created: boolean;
  required_deposit_amount: DecimalString;
  onboarding: InvestmentOnboardingResponse;
}

export interface InvestmentDepositResponse {
  deposit_id: string;
  amount: DecimalString;
  balance_after: DecimalString;
  required_deposit_amount: DecimalString;
  onboarding: InvestmentOnboardingResponse;
}

export interface PriceResponse {
  stock_code: string;
  price: DecimalString;
  previous_close: DecimalString | null;
  change_amount: DecimalString | null;
  change_rate: DecimalString | null;
  volume: number | null;
  source: "KIS" | "REDIS" | string;
  as_of: string;
}

export type StockChartPeriod = "1D" | "1W" | "3M" | "6M" | "1Y" | "5Y";

export interface StockSummaryResponse {
  stock_code: string;
  stock_name: string;
  market: string;
  sector: string | null;
  listing_date: string | null;
  listed_shares: number | null;
  security_type: string | null;
  description: string | null;
  price: DecimalString | null;
  previous_close: DecimalString | null;
  change_amount: DecimalString | null;
  change_rate: DecimalString | null;
  volume: number | null;
  market_cap: DecimalString | null;
  per: DecimalString | null;
  pbr: DecimalString | null;
  roe: DecimalString | null;
  dividend_yield: DecimalString | null;
  financial_year: string | null;
  as_of: string | null;
  sources: Record<string, string | null>;
}

export interface StockChartItemResponse {
  date: string;
  open: DecimalString;
  high: DecimalString;
  low: DecimalString;
  close: DecimalString;
  volume: number;
}

export interface StockChartResponse {
  stock_code: string;
  period: StockChartPeriod;
  source: string;
  as_of: string;
  items: StockChartItemResponse[];
}

export interface PositionResponse {
  stock_code: string;
  stock_name: string | null;
  sector: string | null;
  quantity: DecimalString;
  average_price: DecimalString;
  current_price: DecimalString;
  previous_close: DecimalString | null;
  change_rate: DecimalString | null;
  purchase_amount: DecimalString;
  evaluation_amount: DecimalString;
  unrealized_profit: DecimalString;
  return_rate: DecimalString;
  realized_profit: DecimalString;
  weight: DecimalString;
  today_profit: DecimalString | null;
  price_source: string;
  price_as_of: string;
}

export interface PortfolioContributionResponse {
  stock_code: string;
  stock_name: string | null;
  amount: DecimalString;
  share_rate: DecimalString | null;
}

export interface RebalancingProposalResponse {
  proposal_key: string;
  stock_code: string;
  stock_name: string | null;
  current_weight: DecimalString;
  target_weight: DecimalString;
  weight_diff: DecimalString;
  action: "BUY" | "SELL";
  recommended_amount: DecimalString;
}

export interface PortfolioResponse {
  account_id: string;
  cash_balance: DecimalString;
  total_purchase_amount: DecimalString;
  total_evaluation_amount: DecimalString;
  total_assets: DecimalString;
  unrealized_profit: DecimalString;
  realized_profit: DecimalString;
  return_rate: DecimalString;
  today_profit: DecimalString | null;
  top_contributor: PortfolioContributionResponse | null;
  contributions: PortfolioContributionResponse[];
  strategy_targets_available: boolean;
  rebalancing_proposals: RebalancingProposalResponse[];
  positions: PositionResponse[];
  invested_principal?: DecimalString;
  valuation_profit?: DecimalString;
  withdrawable_amount?: DecimalString;
  settlement_mode?: "VIRTUAL";
}

export type PortfolioHistoryPeriod = "1M" | "3M" | "1Y" | "ALL";

export interface PortfolioHistoryResponse {
  account_id: string;
  period: PortfolioHistoryPeriod;
  benchmark_name: string;
  items: Array<{
    date: string;
    total_assets: DecimalString;
    portfolio_return_rate: DecimalString;
    benchmark_return_rate: DecimalString | null;
  }>;
}

export interface StockEvaluationAxisResponse {
  key:
    | "stability"
    | "financial_health"
    | "growth"
    | "defense"
    | "diversification";
  label: string;
  score: number | null;
  status: "AVAILABLE" | "UNAVAILABLE";
  basis: string;
}

export interface StockEvaluationResponse {
  account_id: string;
  stock_code: string;
  stock_name: string | null;
  feature_version: "stock-feature-v1";
  as_of: string | null;
  target_weight: DecimalString | null;
  role_summary: string | null;
  axes: StockEvaluationAxisResponse[];
  sources: Array<"KRX" | "OpenDART" | "Portfolio">;
}

export interface RebalancingDecisionResponse {
  id: string;
  account_id: string;
  proposal_key: string;
  strategy_id: string | null;
  stock_code: string;
  stock_name: string | null;
  action: "BUY" | "SELL";
  current_weight: DecimalString;
  target_weight: DecimalString;
  weight_diff: DecimalString;
  recommended_amount: DecimalString;
  decision: "ACCEPTED" | "HELD";
  baseline_snapshot_date: string | null;
  actual_portfolio_return_rate: DecimalString | null;
  outcome_as_of: string | null;
  created_at: string;
}

export interface RebalancingDecisionHistoryResponse {
  account_id: string;
  period_label: "최근 6개월";
  proposed: number;
  accepted: number;
  held: number;
  items: RebalancingDecisionResponse[];
}

export interface RebalancingDecisionCreateRequest {
  account_id: string;
  stock_code: string;
  proposal_key: string;
  decision: "ACCEPTED" | "HELD";
  idempotency_key: string;
}

export interface OrderCreateRequest {
  account_id: string;
  stock_code: string;
  side: "BUY" | "SELL";
  order_type: "MARKET";
  quantity: number;
  idempotency_key: string;
}

export interface OrderResponse {
  id: string;
  account_id: string;
  stock_code: string;
  side: "BUY" | "SELL";
  order_type: string;
  quantity: DecimalString;
  status: string;
  requested_price: DecimalString | null;
  requested_at: string;
}

export interface ExecutionResponse {
  id: number;
  order_id: string;
  stock_code: string;
  stock_name: string | null;
  side: "BUY" | "SELL";
  quantity: DecimalString;
  execution_price: DecimalString;
  executed_at: string;
}

export interface InvestorAnswerRequest {
  question_id: string;
  option_id: string;
}

export interface InvestorProfileAnalyzeRequest {
  questionnaire_version: string;
  answers: InvestorAnswerRequest[];
}

export interface InvestorTraitsResponse {
  stability: number;
  return_seeking: number;
  horizon: number;
}

export interface InvestorProfileResponse {
  assessment_id: string;
  questionnaire_version: string;
  analysis_version: "v1" | "v2";
  /** v2부터 백엔드 고정 점수표로 계산한 최종 위험 점수. 기존 v1 결과는 null이다. */
  risk_score: number | null;
  profile_type:
    | "안정추구형"
    | "안정투자형"
    | "중립투자형"
    | "성장추구형"
    | "공격투자형";
  tendency_line: string;
  description: string;
  traits: InvestorTraitsResponse;
  analysis_summary: string[];
  model_version: string;
  created_at: string;
}

export type StrategyRecommendationMatchLevel = "BEST" | "GOOD" | "CAUTION";

export interface StrategyRecommendationItemResponse {
  strategy_id: string;
  rank: number;
  /** 예상수익률이 아니라 투자성향과 전략의 적합도(0~1)다. */
  score: number;
  match_level: StrategyRecommendationMatchLevel;
  reason: string;
  caution: string;
}

export interface StrategyRecommendationResponse {
  recommendation_id: string;
  assessment_id: string;
  primary: StrategyRecommendationItemResponse;
  alternatives: StrategyRecommendationItemResponse[];
  model_version: string;
  dataset_version: string;
  recommendation_version: "v1";
  created_at: string;
}

export interface ModelRecommendationItemResponse {
  symbol: string;
  stock_name: string | null;
  score: number;
  rank: number;
  target_weight: number;
  reason: string;
}

export interface ModelRecommendationSnapshotResponse {
  as_of: string;
  generated_at: string;
  model_version: string;
  data_version: string;
  status: "ready" | "unavailable";
  market_regime: "risk_on" | "neutral" | "risk_off";
  source: "generated" | "fallback";
  is_stale: boolean;
  recommendations: ModelRecommendationItemResponse[];
}

export interface ModelRecommendationApplyResponse {
  account_id: string;
  strategy_id: "momentum";
  as_of: string;
  target_count: number;
  orders_created: number;
  status: "APPLIED" | "PROPOSAL_ONLY" | "ALREADY_APPLIED";
}

export interface ChatHistoryMessageRequest {
  role: "user" | "assistant";
  content: string;
}

export interface ChatScreenContextRequest {
  screen: string;
  stock_code?: string;
  strategy_id?: string;
  account_id?: string;
}

export interface ChatMessageResponse {
  message_id: string;
  status: "COMPLETED" | "NEEDS_CLARIFICATION" | "REFUSED";
  text: string;
  caution: string | null;
  suggested_questions: string[];
  model_version: string;
  generated_at: string;
}

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      "NETWORK_ERROR",
      "서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.",
      0,
    );
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      code?: string;
      message?: string;
    } | null;
    throw new ApiError(
      body?.code ?? "API_ERROR",
      body?.message ?? "요청을 처리하지 못했습니다.",
      response.status,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function createChatMessageApi(
  message: string,
  history: ChatHistoryMessageRequest[],
  context: ChatScreenContextRequest,
  token?: string | null,
  signal?: AbortSignal,
): Promise<ChatMessageResponse> {
  return request<ChatMessageResponse>(
    "/chat/messages",
    {
      method: "POST",
      body: JSON.stringify({ message, history: history.slice(-10), context }),
      signal,
    },
    token,
  );
}

export async function loginApi(
  userId: string,
  password: string,
): Promise<string> {
  const result = await request<{ access_token: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, password }),
  });
  return result.access_token;
}

export function currentUserApi(token: string): Promise<AuthUser> {
  return request<AuthUser>("/auth/me", {}, token);
}

export function signupApi(payload: SignupPayload): Promise<AuthUser> {
  return request<AuthUser>("/auth/signup", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function sendEmailVerificationApi(
  email: string,
): Promise<EmailVerificationSendResponse> {
  return request<EmailVerificationSendResponse>(
    "/auth/email-verifications/send",
    {
      method: "POST",
      body: JSON.stringify({ email }),
    },
  );
}

export function verifyEmailVerificationApi(
  verificationId: string,
  code: string,
): Promise<EmailVerificationVerifyResponse> {
  return request<EmailVerificationVerifyResponse>(
    "/auth/email-verifications/verify",
    {
      method: "POST",
      body: JSON.stringify({ verification_id: verificationId, code }),
    },
  );
}

export function signupTermsApi(): Promise<SignupTerm[]> {
  return request<SignupTerm[]>("/auth/terms");
}

export function logoutApi(token: string): Promise<void> {
  return request<void>("/auth/logout", { method: "POST" }, token);
}

export interface StrategyResponse {
  id: string;
  name: string;
  description: string;
  risk_level: string;
  rebalance_cycle: string;
}

/** 실 전략 카탈로그 — public(로그인 불필요) */
export function getStrategiesApi(): Promise<StrategyResponse[]> {
  return request<StrategyResponse[]>("/strategies");
}

export function getMyAccountApi(
  token: string,
  mode: AccountOperationMode,
): Promise<AccountResponse> {
  return request<AccountResponse>(
    `/accounts/me?operation_mode=${mode}`,
    {},
    token,
  );
}

export function createAccountApi(
  accountName: string,
  mode: AccountOperationMode,
  token: string,
): Promise<AccountResponse> {
  return request<AccountResponse>(
    "/accounts",
    {
      method: "POST",
      body: JSON.stringify({ account_name: accountName, operation_mode: mode }),
    },
    token,
  );
}

export function depositAccountCashApi(
  accountId: string,
  amount: number,
  idempotencyKey: string,
  token: string,
): Promise<AccountCashDepositResponse> {
  return request<AccountCashDepositResponse>(
    `/accounts/${encodeURIComponent(accountId)}/deposits`,
    {
      method: "POST",
      body: JSON.stringify({ amount, idempotency_key: idempotencyKey }),
    },
    token,
  );
}

export function getFundSummaryApi(
  accountId: string,
  token: string,
): Promise<FundSummaryResponse> {
  return request<FundSummaryResponse>(
    `/accounts/${encodeURIComponent(accountId)}/funds`,
    {},
    token,
  );
}

export function createAdditionalInvestmentApi(
  accountId: string,
  payload: FundOperationRequest,
  token: string,
): Promise<FundOperationResponse> {
  return request<FundOperationResponse>(
    `/accounts/${encodeURIComponent(accountId)}/additional-investments`,
    { method: "POST", body: JSON.stringify(payload) },
    token,
  );
}

export function createWithdrawalApi(
  accountId: string,
  payload: FundOperationRequest,
  token: string,
): Promise<FundOperationResponse> {
  return request<FundOperationResponse>(
    `/accounts/${encodeURIComponent(accountId)}/withdrawals`,
    { method: "POST", body: JSON.stringify(payload) },
    token,
  );
}

export function selectStrategyApi(
  accountId: string,
  strategyId: string,
  token: string,
): Promise<AccountResponse> {
  return request<AccountResponse>(
    `/accounts/${encodeURIComponent(accountId)}/strategy`,
    {
      method: "PUT",
      body: JSON.stringify({ strategy_id: strategyId }),
    },
    token,
  );
}

/** 아직 등급을 한 번도 고른 적 없으면 404 CAR_GOAL_NOT_SET을 던진다 — 호출부에서 잡아 "최초 진입" 상태로 다룬다. */
export function getCarGoalApi(token: string): Promise<CarGoalResponse> {
  return request<CarGoalResponse>("/me/car-goal", {}, token);
}

export function upsertCarGoalApi(
  payload: CarGoalUpsertRequest,
  token: string,
): Promise<CarGoalResponse> {
  return request<CarGoalResponse>(
    "/me/car-goal",
    { method: "PUT", body: JSON.stringify(payload) },
    token,
  );
}

export function getInvestmentTermsApi(
  strategyId: string,
  token: string,
): Promise<InvestmentTermResponse[]> {
  return request<InvestmentTermResponse[]>(
    `/investment/terms?strategy_id=${encodeURIComponent(strategyId)}`,
    {},
    token,
  );
}

export function createInvestmentOnboardingApi(
  strategyId: string,
  investmentAmount: number,
  operationMode: AccountOperationMode,
  token: string,
): Promise<InvestmentOnboardingResponse> {
  return request<InvestmentOnboardingResponse>(
    "/investment/onboardings",
    {
      method: "POST",
      body: JSON.stringify({
        strategy_id: strategyId,
        investment_amount: investmentAmount,
        operation_mode: operationMode,
      }),
    },
    token,
  );
}

export function agreeInvestmentTermsApi(
  onboardingId: string,
  agreements: SignupPayload["agreements"],
  token: string,
): Promise<InvestmentOnboardingResponse> {
  return request<InvestmentOnboardingResponse>(
    `/investment/onboardings/${encodeURIComponent(onboardingId)}/agreements`,
    { method: "POST", body: JSON.stringify({ agreements }) },
    token,
  );
}

export function prepareInvestmentAccountApi(
  onboardingId: string,
  token: string,
): Promise<InvestmentAccountPrepareResponse> {
  return request<InvestmentAccountPrepareResponse>(
    `/investment/onboardings/${encodeURIComponent(onboardingId)}/account`,
    {
      method: "POST",
      body: JSON.stringify({ account_name: "나의 가상 투자계좌" }),
    },
    token,
  );
}

export function depositInvestmentCashApi(
  onboardingId: string,
  amount: number,
  idempotencyKey: string,
  token: string,
): Promise<InvestmentDepositResponse> {
  return request<InvestmentDepositResponse>(
    `/investment/onboardings/${encodeURIComponent(onboardingId)}/deposit`,
    {
      method: "POST",
      body: JSON.stringify({ amount, idempotency_key: idempotencyKey }),
    },
    token,
  );
}

export function completeInvestmentOnboardingApi(
  onboardingId: string,
  token: string,
): Promise<InvestmentOnboardingResponse> {
  return request<InvestmentOnboardingResponse>(
    `/investment/onboardings/${encodeURIComponent(onboardingId)}/complete`,
    { method: "POST" },
    token,
  );
}

/** Complete the Backend onboarding state machine with retry-safe deposits. */
export async function startInvestmentApi(
  strategyId: string,
  investmentAmount: number,
  operationMode: AccountOperationMode,
  agreements: SignupPayload["agreements"],
  token: string,
): Promise<InvestmentOnboardingResponse> {
  let onboarding = await createInvestmentOnboardingApi(
    strategyId,
    investmentAmount,
    operationMode,
    token,
  );
  if (onboarding.status === "COMPLETED") return onboarding;

  if (!onboarding.terms_completed) {
    const requiredAgreements = agreements.filter(
      (agreement) => agreement.agreed,
    );
    if (requiredAgreements.length === 0) {
      throw new ApiError(
        "INVESTMENT_TERMS_UNAVAILABLE",
        "확인한 투자 필수 약관이 없습니다.",
        400,
      );
    }
    onboarding = await agreeInvestmentTermsApi(
      onboarding.id,
      requiredAgreements,
      token,
    );
  }

  const prepared = await prepareInvestmentAccountApi(onboarding.id, token);
  const requiredDeposit = Number(prepared.required_deposit_amount);
  if (!Number.isFinite(requiredDeposit) || requiredDeposit < 0) {
    throw new ApiError(
      "INVALID_REQUIRED_DEPOSIT",
      "필요 입금액을 확인할 수 없습니다.",
      500,
    );
  }
  if (requiredDeposit > 0) {
    await depositInvestmentCashApi(
      onboarding.id,
      requiredDeposit,
      `investment-${onboarding.id}-${requiredDeposit}`,
      token,
    );
  }
  return completeInvestmentOnboardingApi(onboarding.id, token);
}

const priceResponseCache = new Map<
  string,
  { expiresAt: number; token: string; value: PriceResponse }
>();
const priceRequests = new Map<
  string,
  { token: string; promise: Promise<PriceResponse> }
>();

export function getStockPriceApi(
  stockCode: string,
  token: string,
): Promise<PriceResponse> {
  const cached = priceResponseCache.get(stockCode);
  if (cached && cached.token === token && cached.expiresAt > Date.now())
    return Promise.resolve(cached.value);
  const pending = priceRequests.get(stockCode);
  if (pending?.token === token) return pending.promise;

  let next: Promise<PriceResponse>;
  next = request<PriceResponse>(
    `/market/stocks/${encodeURIComponent(stockCode)}/price`,
    {},
    token,
  )
    .then((value) => {
      priceResponseCache.set(stockCode, {
        value,
        token,
        expiresAt: Date.now() + 3_000,
      });
      return value;
    })
    .finally(() => {
      if (priceRequests.get(stockCode)?.promise === next)
        priceRequests.delete(stockCode);
    });
  priceRequests.set(stockCode, { token, promise: next });
  return next;
}

export function getStockSummaryApi(
  stockCode: string,
  token: string,
): Promise<StockSummaryResponse> {
  return request<StockSummaryResponse>(
    `/market/stocks/${encodeURIComponent(stockCode)}/summary`,
    {},
    token,
  );
}

export function getStockChartApi(
  stockCode: string,
  period: StockChartPeriod,
  token: string,
): Promise<StockChartResponse> {
  return request<StockChartResponse>(
    `/market/stocks/${encodeURIComponent(stockCode)}/chart?period=${encodeURIComponent(period)}`,
    {},
    token,
  );
}

export function getPortfolioApi(
  accountId: string,
  token: string,
): Promise<PortfolioResponse> {
  return request<PortfolioResponse>(
    `/portfolio?account_id=${encodeURIComponent(accountId)}`,
    {},
    token,
  );
}

export function getPortfolioHistoryApi(
  accountId: string,
  period: PortfolioHistoryPeriod,
  token: string,
): Promise<PortfolioHistoryResponse> {
  return request<PortfolioHistoryResponse>(
    `/portfolio/history?account_id=${encodeURIComponent(accountId)}&period=${period}`,
    {},
    token,
  );
}

export interface PortfolioComparisonAccountResponse {
  account_id: string;
  account_name: string;
  operation_mode: AccountOperationMode;
  strategy_id: string | null;
  baseline_assets: DecimalString | null;
  current_assets: DecimalString | null;
  return_rate: DecimalString | null;
}

export interface PortfolioComparisonMetricsResponse {
  return_rate_gap: DecimalString;
  asset_gap: DecimalString;
  leader: "AI_AUTO" | "MY_INVESTMENT" | "TIE";
}

export interface PortfolioComparisonAIAnalysisResponse {
  status: "AVAILABLE" | "UNAVAILABLE";
  headline: string | null;
  summary: string;
  key_points: string[];
  caution: string | null;
  model_version: string | null;
  generated_at: string | null;
}

export interface PortfolioComparisonResponse {
  comparison_status: "AVAILABLE" | "INSUFFICIENT_DATA";
  period: PortfolioHistoryPeriod;
  baseline_date: string | null;
  as_of: string | null;
  observation_count: number;
  accounts: {
    ai_auto: PortfolioComparisonAccountResponse;
    my_investment: PortfolioComparisonAccountResponse;
  };
  metrics: PortfolioComparisonMetricsResponse | null;
  ai_analysis: PortfolioComparisonAIAnalysisResponse;
}

/** 자동투자(AUTO) vs 반자동(SEMI_AUTO) 계좌 비교 — 두 계좌가 모두 있어야 하고, 없으면 백엔드가
 *  409 COMPARISON_ACCOUNTS_REQUIRED를 반환한다(ApiError.code로 구분). */
export function getPortfolioComparisonApi(
  period: PortfolioHistoryPeriod,
  token: string,
): Promise<PortfolioComparisonResponse> {
  return request<PortfolioComparisonResponse>(
    `/portfolio/comparison?period=${period}`,
    {},
    token,
  );
}

export function getStockEvaluationApi(
  accountId: string,
  stockCode: string,
  token: string,
): Promise<StockEvaluationResponse> {
  return request<StockEvaluationResponse>(
    `/portfolio/stock-evaluation?account_id=${encodeURIComponent(accountId)}&stock_code=${encodeURIComponent(stockCode)}`,
    {},
    token,
  );
}

export function getRebalancingDecisionsApi(
  accountId: string,
  token: string,
): Promise<RebalancingDecisionHistoryResponse> {
  return request<RebalancingDecisionHistoryResponse>(
    `/portfolio/decisions?account_id=${encodeURIComponent(accountId)}`,
    {},
    token,
  );
}

export function createRebalancingDecisionApi(
  payload: RebalancingDecisionCreateRequest,
  token: string,
): Promise<RebalancingDecisionResponse> {
  return request<RebalancingDecisionResponse>(
    "/portfolio/decisions",
    { method: "POST", body: JSON.stringify(payload) },
    token,
  );
}

export function createOrderApi(
  payload: OrderCreateRequest,
  token: string,
): Promise<OrderResponse> {
  return request<OrderResponse>(
    "/orders",
    { method: "POST", body: JSON.stringify(payload) },
    token,
  );
}

export function getOrdersApi(
  accountId: string,
  token: string,
): Promise<OrderResponse[]> {
  return request<OrderResponse[]>(
    `/orders?account_id=${encodeURIComponent(accountId)}`,
    {},
    token,
  );
}

export function getExecutionsApi(
  accountId: string,
  token: string,
): Promise<ExecutionResponse[]> {
  return request<ExecutionResponse[]>(
    `/executions?account_id=${encodeURIComponent(accountId)}`,
    {},
    token,
  );
}

/** AI가 실제로 문항 응답을 분석해 투자성향을 산출·저장한다(investor_profile_assessments 테이블).
 *  AI_PERSONALIZATION 약관에 동의하지 않은 사용자는 403(AI_PERSONALIZATION_CONSENT_REQUIRED)을 받는다.
 *  실패 결과를 임의 성향으로 대체하지 않고 호출 화면에서 오류·재시도 상태로 처리한다. */
export function analyzeInvestorProfileApi(
  payload: InvestorProfileAnalyzeRequest,
  token: string,
): Promise<InvestorProfileResponse> {
  return request<InvestorProfileResponse>(
    "/investor-profile/analyze",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function latestInvestorProfileApi(
  token: string,
): Promise<InvestorProfileResponse> {
  return request<InvestorProfileResponse>(
    "/investor-profile/me/latest",
    {},
    token,
  );
}

export function getLatestModelRecommendationsApi(
  token: string,
): Promise<ModelRecommendationSnapshotResponse> {
  return request<ModelRecommendationSnapshotResponse>(
    "/model-recommendations/latest",
    {},
    token,
  );
}

export function applyLatestModelRecommendationsApi(
  accountId: string,
  token: string,
): Promise<ModelRecommendationApplyResponse> {
  return request<ModelRecommendationApplyResponse>(
    "/model-recommendations/latest/apply",
    {
      method: "POST",
      body: JSON.stringify({ account_id: accountId }),
    },
    token,
  );
}

/** 저장된 투자성향 assessment를 실제 AI 전략 추천에 연결한다. Backend가 동일 입력을 멱등 처리한다. */
export function createStrategyRecommendationApi(
  assessmentId: string,
  token: string,
): Promise<StrategyRecommendationResponse> {
  return request<StrategyRecommendationResponse>(
    "/strategy-recommendations",
    {
      method: "POST",
      body: JSON.stringify({ assessment_id: assessmentId }),
    },
    token,
  );
}
