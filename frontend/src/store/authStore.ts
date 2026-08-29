import { create } from 'zustand';
import {
  currentUserApi, latestInvestorProfileApi, loginApi, logoutApi, signupApi, TOKEN_STORAGE_KEY,
  ApiError, type AuthUser, type SignupPayload,
} from '../lib/backendApi';
import { mapInvestorProfileResponse, type InvestorProfileResult } from '../lib/investorProfile';

interface AuthState {
  isLoggedIn: boolean;
  isHydrating: boolean;
  user: AuthUser | null;
  accessToken: string | null;
  investorProfileCompleted: boolean;
  investorProfileCompletedAt: string | null;
  investorAssessmentId: string | null;
  investorType: string | null;
  investorRiskScore: number | null;
  investorTendencyLine: string | null;
  investorDescription: string | null;
  investorTraits: InvestorProfileResult['traits'] | null;
  /** 이번 세션에서 방금 진단을 마쳤을 때만 채워진다 — 재로그인으로 복원된 경우 백엔드가 원문 답변을
   *  내려주지 않으므로 항상 null 이다(InvestorProfileCheck 는 이 경우 관련 행을 숨긴다). */
  investorAnswers: number[] | null;
  /** /investor-profile/me/latest 조회가 진행 중인 동안 true — 이 값이 true 인 동안은 화면(Portfolio.tsx 등)이
   *  investorProfileCompleted=false 를 "진짜 미진단"으로 오판하지 않아야 한다(조회가 끝나기 전 스냅샷일 뿐이므로). */
  isInvestorProfileHydrating: boolean;
  investorProfileHydrationError: string | null;
  hydrateInvestorProfile: () => Promise<void>;
  initialize: () => Promise<void>;
  login: (userId: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  register: (payload: SignupPayload) => Promise<void>;
  completeInvestorProfile: (
    profile: InvestorProfileResult,
    answers: number[],
    completedAt: string,
    assessmentId: string,
  ) => void;
  resetInvestorProfile: () => void;
}

const savedToken = localStorage.getItem(TOKEN_STORAGE_KEY);

/** App.tsx 가 화면 상태(screen/strategyId/stockCode 등)를 저장하는 sessionStorage 키 — 사용자별로
 *  나뉘어 있지 않은 공용 키라, 로그아웃(명시적 버튼 또는 401 자동 로그아웃)하거나 만료된 토큰으로
 *  새로고침될 때 함께 지워야 다음에 로그인하는(같은 브라우저의 다른) 사용자가 이전 화면 상태를 이어받지 않는다. */
const APP_SESSION_NAV_KEY = 'fein.session-nav';

/** 사용자가 바뀌는 모든 지점(로그아웃, 새 로그인 시작, 인증 실패)에서 함께 리셋해야 하는 투자성향 필드 —
 *  A 사용자의 값이 B 사용자에게 잠깐이라도 남아있으면 B 가 이미 진단을 마친 것처럼 잘못 판정될 수 있다. */
const INVESTOR_PROFILE_RESET = {
  investorProfileCompleted: false,
  investorProfileCompletedAt: null,
  investorAssessmentId: null,
  investorType: null,
  investorRiskScore: null,
  investorTendencyLine: null,
  investorDescription: null,
  investorTraits: null,
  investorAnswers: null,
  investorProfileHydrationError: null,
} satisfies Partial<AuthState>;

/** InvestorProfileResult(화면 공용 모양) → AuthState 의 flat 필드로 펼친다. */
function toInvestorProfileFields(profile: InvestorProfileResult) {
  return {
    investorType: profile.type,
    investorRiskScore: profile.riskScore,
    investorTendencyLine: profile.tendencyLine,
    investorDescription: profile.description,
    investorTraits: profile.traits,
  } satisfies Partial<AuthState>;
}

/** 로그인 직후/새로고침 복원 시 이미 저장된 투자성향 진단이 있으면 investorProfileCompleted 를 되살린다.
 *  이 값은 완료 즉시(completeInvestorProfile) 로컬에서도 true 가 되지만, 백엔드에 저장은 되어도
 *  로컬 상태 자체는 세션이 새로 시작되면 초기화되므로(새로고침·재로그인) 매번 다시 확인해야 한다.
 *  진단 기록이 없으면(404)은 미완료 상태로 유지하고, 그 밖의 API/네트워크 오류는 추적 가능한
 *  오류 코드를 상태에 남긴다 — 어느 경우에도 로그인 자체를 막지는 않는다.
 *
 *  race 방지: 이 함수는 fire-and-forget(void)로 호출되기 때문에, 응답이 오는 사이 사용자가 로그아웃하거나
 *  다른 사용자로 다시 로그인하면 accessToken 이 바뀐다. 응답을 반영하기 직전 get().accessToken 이 호출 시점의
 *  token 과 여전히 같은지 확인해서, 이미 지나가버린(stale) 응답이 새 사용자의 상태를 덮어쓰지 않게 한다. */
async function hydrateInvestorProfile(
  token: string,
  set: (partial: Partial<AuthState>) => void,
  get: () => AuthState,
) {
  set({ isInvestorProfileHydrating: true });
  try {
    const profile = await latestInvestorProfileApi(token);
    if (get().accessToken !== token) return; // 그 사이 로그아웃/다른 사용자 로그인 — 이 응답은 버린다
    set({
      investorProfileCompleted: true,
      investorProfileCompletedAt: profile.created_at,
      investorAssessmentId: profile.assessment_id,
      ...toInvestorProfileFields(mapInvestorProfileResponse(profile)),
      investorProfileHydrationError: null,
      isInvestorProfileHydrating: false,
    });
  } catch (error) {
    // 404(진단 기록 없음)와 네트워크/API 오류를 구분한다. 로그인 자체는 막지 않지만,
    // 개발 환경에서는 원인을 남기고 상태에도 보존해 fire-and-forget 실패를 추적할 수 있게 한다.
    if (get().accessToken !== token) return;
    const errorCode = error instanceof ApiError ? error.code : "UNKNOWN_ERROR";
    if (import.meta.env.DEV && errorCode !== "INVESTOR_PROFILE_NOT_FOUND") {
      console.warn("[auth] investor profile hydration failed", error);
    }
    set({
      isInvestorProfileHydrating: false,
      investorProfileHydrationError:
        error instanceof ApiError && error.status === 404 ? null : errorCode,
    });
  }
}

let activeHydration: { token: string; promise: Promise<void> } | null = null;

function startInvestorProfileHydration(
  token: string,
  set: (partial: Partial<AuthState>) => void,
  get: () => AuthState,
) {
  if (activeHydration?.token === token) return activeHydration.promise;
  const promise = hydrateInvestorProfile(token, set, get).finally(() => {
    if (activeHydration?.promise === promise) activeHydration = null;
  });
  activeHydration = { token, promise };
  return promise;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  isLoggedIn: false,
  isHydrating: Boolean(savedToken),
  user: null,
  accessToken: savedToken,
  ...INVESTOR_PROFILE_RESET,
  isInvestorProfileHydrating: false,
  investorProfileHydrationError: null,

  initialize: async () => {
    const token = get().accessToken;
    if (!token) { set({ isHydrating: false }); return; }
    try {
      const user = await currentUserApi(token);
      set({ user, isLoggedIn: true, isHydrating: false });
      void startInvestorProfileHydration(token, set, get);
    } catch {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      sessionStorage.removeItem(APP_SESSION_NAV_KEY);
      set({ user: null, accessToken: null, isLoggedIn: false, isHydrating: false, ...INVESTOR_PROFILE_RESET });
    }
  },

  login: async (userId, password) => {
    const token = await loginApi(userId, password);
    const user = await currentUserApi(token);
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
    // 새 로그인을 시작하는 시점에 이전 사용자(또는 이전 세션)의 투자성향 상태를 먼저 지운다 — 아래
    // hydrateInvestorProfile 이 끝나기 전까지 잠깐이라도 이전 값이 새 사용자 것처럼 보이지 않게 한다.
    set({ accessToken: token, user, isLoggedIn: true, isHydrating: false, ...INVESTOR_PROFILE_RESET });
    void startInvestorProfileHydration(token, set, get);
  },

  logout: async () => {
    const token = get().accessToken;
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    sessionStorage.removeItem(APP_SESSION_NAV_KEY);
    set({
      accessToken: null, user: null, isLoggedIn: false,
      ...INVESTOR_PROFILE_RESET, isInvestorProfileHydrating: false,
    });
    if (token) await logoutApi(token).catch(() => undefined);
  },

  register: async (payload) => {
    await signupApi(payload);
    await get().login(payload.user_id, payload.password);
  },

  hydrateInvestorProfile: async () => {
    const token = get().accessToken;
    if (!token) {
      set({ isInvestorProfileHydrating: false });
      return;
    }
    await startInvestorProfileHydration(token, set, get);
  },

  completeInvestorProfile: (profile, answers, completedAt, assessmentId) => set({
    investorProfileCompleted: true,
    investorProfileCompletedAt: completedAt,
    investorAssessmentId: assessmentId,
    ...toInvestorProfileFields(profile),
    investorAnswers: answers,
  }),
  resetInvestorProfile: () => set({ ...INVESTOR_PROFILE_RESET }),
}));
