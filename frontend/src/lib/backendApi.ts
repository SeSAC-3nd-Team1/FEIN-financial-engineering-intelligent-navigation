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

export interface AccountResponse {
  id: string;
  account_name: string;
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
  quantity: number;
  average_price: DecimalString;
  current_price: DecimalString;
  purchase_amount: DecimalString;
  evaluation_amount: DecimalString;
  unrealized_profit: DecimalString;
  return_rate: DecimalString;
  realized_profit: DecimalString;
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
  positions: PositionResponse[];
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
  quantity: number;
  status: string;
  requested_price: DecimalString | null;
  requested_at: string;
}

export interface ExecutionResponse {
  id: number;
  order_id: string;
  stock_code: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  execution_price: DecimalString;
  executed_at: string;
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

export function getMyAccountApi(token: string): Promise<AccountResponse> {
  return request<AccountResponse>('/accounts/me', {}, token);
}

export function createAccountApi(accountName: string, token: string): Promise<AccountResponse> {
  return request<AccountResponse>('/accounts', {
    method: 'POST', body: JSON.stringify({ account_name: accountName }),
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

export function createOrderApi(payload: OrderCreateRequest, token: string): Promise<OrderResponse> {
  return request<OrderResponse>('/orders', { method: 'POST', body: JSON.stringify(payload) }, token);
}

export function getOrdersApi(accountId: string, token: string): Promise<OrderResponse[]> {
  return request<OrderResponse[]>(`/orders?account_id=${encodeURIComponent(accountId)}`, {}, token);
}

export function getExecutionsApi(accountId: string, token: string): Promise<ExecutionResponse[]> {
  return request<ExecutionResponse[]>(`/executions?account_id=${encodeURIComponent(accountId)}`, {}, token);
}
