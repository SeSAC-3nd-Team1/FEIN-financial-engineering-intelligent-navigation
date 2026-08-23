import { create } from 'zustand';
import {
  currentUserApi, loginApi, logoutApi, signupApi, TOKEN_STORAGE_KEY,
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
    } catch {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      set({ user: null, accessToken: null, isLoggedIn: false, isHydrating: false });
    }
  },

  login: async (userId, password) => {
    const token = await loginApi(userId, password);
    const user = await currentUserApi(token);
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
    set({ accessToken: token, user, isLoggedIn: true, isHydrating: false });
  },

  logout: async () => {
    const token = get().accessToken;
    localStorage.removeItem(TOKEN_STORAGE_KEY);
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
