import { create } from 'zustand';

interface AuthState {
  isLoggedIn: boolean;
  account: { userId: string; password: string } | null;
  /** 투자자 정보(투자성향) 확인 완료 여부 — 실제 투자 시작 전 가드에 쓰인다 */
  investorProfileCompleted: boolean;
  investorProfileCompletedAt: string | null; // ISO 문자열
  investorType: string | null; // MOCK 분류 라벨 (lib/investorProfile.ts)
  investorAnswers: number[] | null; // 7문항 각각 고른 보기 인덱스
  login: () => void;
  logout: () => void;
  /** 회원가입 Step 03에서 만든 아이디/비밀번호를 저장 — 로그인 화면에서 이 값과 대조한다 */
  register: (userId: string, password: string) => void;
  /** 투자자 정보 확인(7문항) 완료 시 결과를 저장 */
  completeInvestorProfile: (type: string, answers: number[], completedAt: string) => void;
  /** "정보가 달라졌어요" — 재진단을 위해 완료 상태만 초기화 (계정 등 다른 상태는 유지) */
  resetInvestorProfile: () => void;
}

/** 로그인 여부 — 헤더의 "전략 둘러보기"/"나의 포트폴리오" 접근 가드에 쓰인다 */
export const useAuthStore = create<AuthState>((set) => ({
  isLoggedIn: false,
  account: null,
  investorProfileCompleted: false,
  investorProfileCompletedAt: null,
  investorType: null,
  investorAnswers: null,
  login: () => set({ isLoggedIn: true }),
  logout: () => set({ isLoggedIn: false }),
  register: (userId, password) => set({ account: { userId, password } }),
  completeInvestorProfile: (type, answers, completedAt) => set({
    investorProfileCompleted: true,
    investorProfileCompletedAt: completedAt,
    investorType: type,
    investorAnswers: answers,
  }),
  resetInvestorProfile: () => set({ investorProfileCompleted: false }),
}));
