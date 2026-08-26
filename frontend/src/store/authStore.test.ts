import { beforeEach, describe, expect, it, vi } from 'vitest';
// authStore.ts 는 모듈 로드 시점에 바로 localStorage 를 읽는데, vitest 기본(node) 환경에는 localStorage 가
// 없다 — jsdom 을 새로 추가하는 대신 최소 polyfill 을 authStore 임포트보다 먼저 실행해 채워둔다.
import '../test/setupStorage';

vi.mock('../lib/backendApi', () => ({
  TOKEN_STORAGE_KEY: 'fein_access_token',
  loginApi: vi.fn(),
  currentUserApi: vi.fn(),
  logoutApi: vi.fn(),
  latestInvestorProfileApi: vi.fn(),
  signupApi: vi.fn(),
}));

import { currentUserApi, latestInvestorProfileApi, loginApi, logoutApi, type InvestorProfileResponse } from '../lib/backendApi';
import { useAuthStore } from './authStore';

/** Promise 를 테스트 코드에서 원하는 시점에 직접 resolve/reject 할 수 있게 감싼다 —
 *  hydration 지연·경합(race) 시나리오를 setTimeout 없이 결정적으로 재현하기 위해 쓴다. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function mockUser(id: number, userId: string) {
  return { id, user_id: userId, name: userId, email: `${userId}@test.com`, account_status: 'ACTIVE' };
}

function mockProfile(overrides: Partial<InvestorProfileResponse> = {}): InvestorProfileResponse {
  return {
    assessment_id: 'assessment-1',
    questionnaire_version: 'v1',
    analysis_version: 'v1',
    profile_type: '안정추구형',
    tendency_line: '지키는 것을 중요하게 생각해요',
    description: '설명',
    traits: { stability: 5, return_seeking: 1, horizon: 1 },
    analysis_summary: ['근거'],
    model_version: 'investor-profile-v1',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

/** fire-and-forget 로 시작되는 hydrateInvestorProfile 의 microtask 가 마저 처리되도록 한 틱 넘긴다. */
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const INITIAL_STATE = useAuthStore.getState();

describe('useAuthStore — 투자성향 상태 관리', () => {
  beforeEach(() => {
    useAuthStore.setState(INITIAL_STATE, true);
    vi.clearAllMocks();
  });

  it('로그아웃하면 투자성향 관련 상태가 모두 초기화된다', async () => {
    vi.mocked(loginApi).mockResolvedValue('token-a');
    vi.mocked(currentUserApi).mockResolvedValue(mockUser(1, 'a'));
    vi.mocked(latestInvestorProfileApi).mockResolvedValue(mockProfile());
    vi.mocked(logoutApi).mockResolvedValue(undefined);

    await useAuthStore.getState().login('a', 'pw');
    await flush();
    const hydrated = useAuthStore.getState();
    expect(hydrated.investorProfileCompleted).toBe(true);
    expect(hydrated.investorType).toBe('안정추구형');
    // 백엔드 응답이 Source of Truth — RiskResult/InvestorProfileCheck가 쓰는 나머지 필드도 그대로 매핑돼야 한다.
    expect(hydrated.investorTendencyLine).toBe('지키는 것을 중요하게 생각해요');
    expect(hydrated.investorDescription).toBe('설명');
    expect(hydrated.investorTraits).toEqual({ stability: 5, returnSeeking: 1, horizon: 1 });

    await useAuthStore.getState().logout();
    const state = useAuthStore.getState();
    expect(state.investorProfileCompleted).toBe(false);
    expect(state.investorProfileCompletedAt).toBeNull();
    expect(state.investorType).toBeNull();
    expect(state.investorTendencyLine).toBeNull();
    expect(state.investorDescription).toBeNull();
    expect(state.investorTraits).toBeNull();
    expect(state.investorAnswers).toBeNull();
    expect(state.isInvestorProfileHydrating).toBe(false);
  });

  it('인증 실패(initialize)로 로그아웃되는 경우에도 투자성향 상태가 초기화된다', async () => {
    // completeInvestorProfile 로 로컬에만 값을 채운 뒤(예: 방금 진단 완료), 토큰 만료로 initialize() 가 실패하는 상황
    useAuthStore.getState().completeInvestorProfile(
      { type: '공격투자형', tendencyLine: '', description: '', traits: { stability: 1, returnSeeking: 5, horizon: 5 } },
      [0, 1, 2],
      '2026-01-01T00:00:00Z',
    );
    useAuthStore.setState({ accessToken: 'expired-token' });
    vi.mocked(currentUserApi).mockRejectedValue(new Error('401'));

    await useAuthStore.getState().initialize();

    const state = useAuthStore.getState();
    expect(state.isLoggedIn).toBe(false);
    expect(state.investorProfileCompleted).toBe(false);
    expect(state.investorType).toBeNull();
    expect(state.investorAnswers).toBeNull();
  });

  it('사용자를 전환하면 이전 사용자의 투자성향이 새 사용자에게 남지 않는다 (latest profile 404 포함)', async () => {
    vi.mocked(loginApi).mockResolvedValueOnce('token-a');
    vi.mocked(currentUserApi).mockResolvedValueOnce(mockUser(1, 'a'));
    vi.mocked(latestInvestorProfileApi).mockResolvedValueOnce(mockProfile());
    await useAuthStore.getState().login('a', 'pw');
    await flush();
    expect(useAuthStore.getState().investorProfileCompleted).toBe(true);

    await useAuthStore.getState().logout();

    // 사용자 B: 진단 기록 없음 — 백엔드는 404 를 던지고 backendApi.ts 는 이를 reject 로 전달한다
    vi.mocked(loginApi).mockResolvedValueOnce('token-b');
    vi.mocked(currentUserApi).mockResolvedValueOnce(mockUser(2, 'b'));
    vi.mocked(latestInvestorProfileApi).mockRejectedValueOnce(new Error('INVESTOR_PROFILE_NOT_FOUND'));
    await useAuthStore.getState().login('b', 'pw');
    await flush();

    const state = useAuthStore.getState();
    expect(state.user?.user_id).toBe('b');
    expect(state.investorProfileCompleted).toBe(false);
    expect(state.investorType).toBeNull();
    expect(state.isInvestorProfileHydrating).toBe(false);
  });

  it('hydration 이 끝나기 전에는 isInvestorProfileHydrating 이 true 로 유지된다', async () => {
    vi.mocked(loginApi).mockResolvedValue('token-a');
    vi.mocked(currentUserApi).mockResolvedValue(mockUser(1, 'a'));
    const slow = deferred<InvestorProfileResponse>();
    vi.mocked(latestInvestorProfileApi).mockReturnValue(slow.promise);

    await useAuthStore.getState().login('a', 'pw');
    // login() 자체는 끝났지만 hydrateInvestorProfile 은 fire-and-forget 이라 아직 진행 중이어야 한다.
    expect(useAuthStore.getState().isInvestorProfileHydrating).toBe(true);
    expect(useAuthStore.getState().investorProfileCompleted).toBe(false);

    slow.resolve(mockProfile());
    await flush();
    expect(useAuthStore.getState().isInvestorProfileHydrating).toBe(false);
    expect(useAuthStore.getState().investorProfileCompleted).toBe(true);
  });

  it('늦게 도착한 이전 사용자의 hydration 응답이 새 사용자 상태를 덮어쓰지 않는다 (race)', async () => {
    // 사용자 A 로그인 — hydrate 응답을 일부러 보류(deferred)한다.
    vi.mocked(loginApi).mockResolvedValueOnce('token-a');
    vi.mocked(currentUserApi).mockResolvedValueOnce(mockUser(1, 'a'));
    const slowA = deferred<InvestorProfileResponse>();
    vi.mocked(latestInvestorProfileApi).mockReturnValueOnce(slowA.promise);
    await useAuthStore.getState().login('a', 'pw');

    // A 의 hydrate 가 응답하기 전에 로그아웃하고 사용자 B 로 로그인 — B 의 hydrate 는 즉시 성공한다.
    await useAuthStore.getState().logout();
    vi.mocked(loginApi).mockResolvedValueOnce('token-b');
    vi.mocked(currentUserApi).mockResolvedValueOnce(mockUser(2, 'b'));
    vi.mocked(latestInvestorProfileApi).mockResolvedValueOnce(
      mockProfile({ profile_type: '공격투자형', assessment_id: 'assessment-2', created_at: '2026-02-02T00:00:00Z' }),
    );
    await useAuthStore.getState().login('b', 'pw');
    await flush();
    expect(useAuthStore.getState().investorType).toBe('공격투자형');

    // 이제서야 A 의 늦은 응답이 도착한다 — 이미 B 로 전환된 상태를 덮어쓰면 안 된다.
    slowA.resolve(mockProfile({ profile_type: '안정추구형' }));
    await flush();

    const state = useAuthStore.getState();
    expect(state.user?.user_id).toBe('b');
    expect(state.investorType).toBe('공격투자형');
    expect(state.investorProfileCompletedAt).toBe('2026-02-02T00:00:00Z');
  });
});
