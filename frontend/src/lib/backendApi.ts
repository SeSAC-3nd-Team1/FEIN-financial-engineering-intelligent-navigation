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
