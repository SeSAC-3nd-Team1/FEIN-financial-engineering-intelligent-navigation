const API_BASE = '/api/v1';
export const TOKEN_STORAGE_KEY = 'fein_access_token';

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
  phone_verified: boolean;
  email_verified: boolean;
  agreements: { term_code: string; version: string; agreed: boolean }[];
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
export type AccountOperationMode = 'AUTO' | 'SEMI_AUTO';

export interface AccountResponse {
  id: string;
  account_name: string;
  operation_mode: AccountOperationMode;
  initial_cash: DecimalString;
  cash_balance: DecimalString;
  status: string;
  selected_strategy_id: string | null;
  created_at: string;
}

export interface PriceResponse {
  stock_code: string;
  price: DecimalString;
  previous_close: DecimalString | null;
  change_amount: DecimalString | null;
  change_rate: DecimalString | null;
  volume: number | null;
  source: 'KIS' | 'REDIS' | string;
  as_of: string;
}

export type StockChartPeriod = '1D' | '1W' | '3M' | '6M' | '1Y' | '5Y';

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
  stock_code: string;
  stock_name: string | null;
  current_weight: DecimalString;
  target_weight: DecimalString;
  weight_diff: DecimalString;
  action: 'BUY' | 'SELL';
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
}

export type PortfolioHistoryPeriod = '1M' | '3M' | '1Y' | 'ALL';

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
  key: 'stability' | 'financial_health' | 'growth' | 'defense' | 'diversification';
  label: string;
  score: number | null;
  status: 'AVAILABLE' | 'UNAVAILABLE';
  basis: string;
}

export interface StockEvaluationResponse {
  account_id: string;
  stock_code: string;
  stock_name: string | null;
  feature_version: 'stock-feature-v1';
  as_of: string | null;
  target_weight: DecimalString | null;
  role_summary: string | null;
  axes: StockEvaluationAxisResponse[];
  sources: Array<'KRX' | 'OpenDART' | 'Portfolio'>;
}

export interface RebalancingDecisionResponse {
  id: string;
  account_id: string;
  strategy_id: string | null;
  stock_code: string;
  stock_name: string | null;
  action: 'BUY' | 'SELL';
  current_weight: DecimalString;
  target_weight: DecimalString;
  weight_diff: DecimalString;
  recommended_amount: DecimalString;
  decision: 'ACCEPTED' | 'HELD';
  baseline_snapshot_date: string | null;
  actual_portfolio_return_rate: DecimalString | null;
  outcome_as_of: string | null;
  created_at: string;
}

export interface RebalancingDecisionHistoryResponse {
  account_id: string;
  period_label: '최근 6개월';
  proposed: number;
  accepted: number;
  held: number;
  items: RebalancingDecisionResponse[];
}

export interface RebalancingDecisionCreateRequest {
  account_id: string;
  stock_code: string;
  decision: 'ACCEPTED' | 'HELD';
  idempotency_key: string;
}

export interface OrderCreateRequest {
  account_id: string;
  stock_code: string;
  side: 'BUY' | 'SELL';
  order_type: 'MARKET';
  quantity: number;
  idempotency_key: string;
}

export interface OrderResponse {
  id: string;
  account_id: string;
  stock_code: string;
  side: 'BUY' | 'SELL';
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
  side: 'BUY' | 'SELL';
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
  analysis_version: 'v1';
  profile_type: '안정추구형' | '안정투자형' | '중립투자형' | '성장추구형' | '공격투자형';
  tendency_line: string;
  description: string;
  traits: InvestorTraitsResponse;
  analysis_summary: string[];
  model_version: string;
  created_at: string;
}

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string | null): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError('NETWORK_ERROR', '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.', 0);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { code?: string; message?: string } | null;
    throw new ApiError(body?.code ?? 'API_ERROR', body?.message ?? '요청을 처리하지 못했습니다.', response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function loginApi(userId: string, password: string): Promise<string> {
  const result = await request<{ access_token: string }>('/auth/login', {
    method: 'POST', body: JSON.stringify({ user_id: userId, password }),
  });
  return result.access_token;
}

export function currentUserApi(token: string): Promise<AuthUser> {
  return request<AuthUser>('/auth/me', {}, token);
}

export function signupApi(payload: SignupPayload): Promise<AuthUser> {
  return request<AuthUser>('/auth/signup', { method: 'POST', body: JSON.stringify(payload) });
}

export function signupTermsApi(): Promise<SignupTerm[]> {
  return request<SignupTerm[]>('/auth/terms');
}

export function logoutApi(token: string): Promise<void> {
  return request<void>('/auth/logout', { method: 'POST' }, token);
}

export function getMyAccountApi(token: string, mode: AccountOperationMode): Promise<AccountResponse> {
  return request<AccountResponse>(`/accounts/me?operation_mode=${mode}`, {}, token);
}

export function createAccountApi(accountName: string, mode: AccountOperationMode, token: string): Promise<AccountResponse> {
  return request<AccountResponse>('/accounts', {
    method: 'POST', body: JSON.stringify({ account_name: accountName, operation_mode: mode }),
  }, token);
}

export function selectStrategyApi(accountId: string, strategyId: string, token: string): Promise<AccountResponse> {
  return request<AccountResponse>(`/accounts/${encodeURIComponent(accountId)}/strategy`, {
    method: 'PUT', body: JSON.stringify({ strategy_id: strategyId }),
  }, token);
}

const priceResponseCache = new Map<string, { expiresAt: number; token: string; value: PriceResponse }>();
const priceRequests = new Map<string, { token: string; promise: Promise<PriceResponse> }>();

export function getStockPriceApi(stockCode: string, token: string): Promise<PriceResponse> {
  const cached = priceResponseCache.get(stockCode);
  if (cached && cached.token === token && cached.expiresAt > Date.now()) return Promise.resolve(cached.value);
  const pending = priceRequests.get(stockCode);
  if (pending?.token === token) return pending.promise;

  let next: Promise<PriceResponse>;
  next = request<PriceResponse>(`/market/stocks/${encodeURIComponent(stockCode)}/price`, {}, token)
    .then((value) => {
      priceResponseCache.set(stockCode, { value, token, expiresAt: Date.now() + 3_000 });
      return value;
    })
    .finally(() => {
      if (priceRequests.get(stockCode)?.promise === next) priceRequests.delete(stockCode);
    });
  priceRequests.set(stockCode, { token, promise: next });
  return next;
}

export function getStockSummaryApi(stockCode: string, token: string): Promise<StockSummaryResponse> {
  return request<StockSummaryResponse>(`/market/stocks/${encodeURIComponent(stockCode)}/summary`, {}, token);
}

export function getStockChartApi(stockCode: string, period: StockChartPeriod, token: string): Promise<StockChartResponse> {
  return request<StockChartResponse>(
    `/market/stocks/${encodeURIComponent(stockCode)}/chart?period=${encodeURIComponent(period)}`,
    {},
    token,
  );
}

export function getPortfolioApi(accountId: string, token: string): Promise<PortfolioResponse> {
  return request<PortfolioResponse>(`/portfolio?account_id=${encodeURIComponent(accountId)}`, {}, token);
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
    '/portfolio/decisions',
    { method: 'POST', body: JSON.stringify(payload) },
    token,
  );
}

export function createOrderApi(payload: OrderCreateRequest, token: string): Promise<OrderResponse> {
  return request<OrderResponse>('/orders', { method: 'POST', body: JSON.stringify(payload) }, token);
}

export function getOrdersApi(accountId: string, token: string): Promise<OrderResponse[]> {
  return request<OrderResponse[]>(`/orders?account_id=${encodeURIComponent(accountId)}`, {}, token);
}

export function getExecutionsApi(accountId: string, token: string): Promise<ExecutionResponse[]> {
  return request<ExecutionResponse[]>(`/executions?account_id=${encodeURIComponent(accountId)}`, {}, token);
}

/** AI가 실제로 문항 응답을 분석해 투자성향을 산출·저장한다(investor_profile_assessments 테이블).
 *  AI_PERSONALIZATION 약관에 동의하지 않은 사용자는 403(AI_PERSONALIZATION_CONSENT_REQUIRED)을 받는다 —
 *  호출부에서 이 실패를 화면 흐름을 막지 않는 best-effort 로 다뤄야 한다. */
export function analyzeInvestorProfileApi(
  payload: InvestorProfileAnalyzeRequest,
  token: string,
): Promise<InvestorProfileResponse> {
  return request<InvestorProfileResponse>('/investor-profile/analyze', {
    method: 'POST', body: JSON.stringify(payload),
  }, token);
}

export function latestInvestorProfileApi(token: string): Promise<InvestorProfileResponse> {
  return request<InvestorProfileResponse>('/investor-profile/me/latest', {}, token);
}
