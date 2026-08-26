import { create } from 'zustand';
import {
  currentUserApi, latestInvestorProfileApi, loginApi, logoutApi, signupApi, TOKEN_STORAGE_KEY,
  type AuthUser, type SignupPayload,
} from '../lib/backendApi';

interface AuthState {
  isLoggedIn: boolean;
  isHydrating: boolean;
  user: AuthUser | null;
  accessToken: string | null;
  investorProfileCompleted: boolean;
  investorProfileCompletedAt: string | null;
  investorType: string | null;
  investorAnswers: number[] | null;
  initialize: () => Promise<void>;
  login: (userId: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  register: (payload: SignupPayload) => Promise<void>;
  completeInvestorProfile: (type: string, answers: number[], completedAt: string) => void;
  resetInvestorProfile: () => void;
}

const savedToken = localStorage.getItem(TOKEN_STORAGE_KEY);

/** App.tsx 가 화면 상태(screen/strategyId/stockCode 등)를 저장하는 sessionStorage 키 — 사용자별로
 *  나뉘어 있지 않은 공용 키라, 로그아웃(명시적 버튼 또는 401 자동 로그아웃)하거나 만료된 토큰으로
 *  새로고침될 때 함께 지워야 다음에 로그인하는(같은 브라우저의 다른) 사용자가 이전 화면 상태를 이어받지 않는다. */
const APP_SESSION_NAV_KEY = 'fein.session-nav';

/** 로그인 직후/새로고침 복원 시 이미 저장된 투자성향 진단이 있으면 investorProfileCompleted 를 되살린다.
 *  이 값은 완료 즉시(completeInvestorProfile) 로컬에서도 true 가 되지만, 백엔드에 저장은 되어도
 *  로컬 상태 자체는 세션이 새로 시작되면 초기화되므로(새로고침·재로그인) 매번 다시 확인해야 한다.
 *  진단 기록이 없으면(404) 또는 조회에 실패하면 조용히 무시하고 미완료 상태를 유지한다 — 로그인 자체를
 *  막을 이유는 아니다. */
async function hydrateInvestorProfile(token: string, set: (partial: Partial<AuthState>) => void) {
  try {
    const profile = await latestInvestorProfileApi(token);
    set({
      investorProfileCompleted: true,
      investorProfileCompletedAt: profile.created_at,
      investorType: profile.profile_type,
    });
  } catch {
    // 진단 기록 없음(404) 또는 일시적 오류 — 미완료 상태를 그대로 둔다.
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  isLoggedIn: false,
  isHydrating: Boolean(savedToken),
  user: null,
  accessToken: savedToken,
  investorProfileCompleted: false,
  investorProfileCompletedAt: null,
  investorType: null,
  investorAnswers: null,

  initialize: async () => {
    const token = get().accessToken;
    if (!token) { set({ isHydrating: false }); return; }
    try {
      const user = await currentUserApi(token);
      set({ user, isLoggedIn: true, isHydrating: false });
      void hydrateInvestorProfile(token, set);
    } catch {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      sessionStorage.removeItem(APP_SESSION_NAV_KEY);
      set({ user: null, accessToken: null, isLoggedIn: false, isHydrating: false });
    }
  },

  login: async (userId, password) => {
    const token = await loginApi(userId, password);
    const user = await currentUserApi(token);
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
    set({ accessToken: token, user, isLoggedIn: true, isHydrating: false });
    void hydrateInvestorProfile(token, set);
  },

  logout: async () => {
    const token = get().accessToken;
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    sessionStorage.removeItem(APP_SESSION_NAV_KEY);
    set({ accessToken: null, user: null, isLoggedIn: false });
    if (token) await logoutApi(token).catch(() => undefined);
  },

  register: async (payload) => {
    await signupApi(payload);
    await get().login(payload.user_id, payload.password);
  },

  completeInvestorProfile: (type, answers, completedAt) => set({
    investorProfileCompleted: true,
    investorProfileCompletedAt: completedAt,
    investorType: type,
    investorAnswers: answers,
  }),
  resetInvestorProfile: () => set({ investorProfileCompleted: false }),
}));
