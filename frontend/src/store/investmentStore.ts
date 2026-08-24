import { create } from 'zustand';
import type { OperationMode } from '../data/fees';

export const INVESTMENT_ONBOARDING_STORAGE_KEY = 'fein_investment_onboarding';

/** MOCK SeSAC증권 연동 계좌 — 실제 증권사 API 연동 전까지 잔액도 프론트 상태로만 관리한다. */
export interface SesacAccount {
  /** 마스킹된 표시용 계좌번호 — 예: "123-****-5678" */
  accountNumber: string;
  /** MOCK 예수금 잔액(원) — 입금 필요 여부 판단에 사용 */
  balance: number;
}

export interface PendingInvestment {
  strategyId: string;
  strategyName: string;
  amount: number;
  mode: OperationMode;
}

interface PersistedOnboarding {
  /** 상품설명서·필수 약관 동의를 완료한 전략 id 목록 — 전략마다 상품설명서가 달라 전략 단위로 저장 */
  termsAcceptedStrategyIds: string[];
  sesacAccount: SesacAccount | null;
  /** "나중에 입금할게요"로 대기 중인 투자 — null이면 대기 중인 입금 없음 */
  pendingInvestment: PendingInvestment | null;
}

const EMPTY_ONBOARDING: PersistedOnboarding = {
  termsAcceptedStrategyIds: [],
  sesacAccount: null,
  pendingInvestment: null,
};

function loadPersisted(): PersistedOnboarding {
  try {
    const raw = localStorage.getItem(INVESTMENT_ONBOARDING_STORAGE_KEY);
    if (!raw) return EMPTY_ONBOARDING;
    return { ...EMPTY_ONBOARDING, ...JSON.parse(raw) };
  } catch {
    return EMPTY_ONBOARDING;
  }
}

function persist(state: PersistedOnboarding) {
  localStorage.setItem(INVESTMENT_ONBOARDING_STORAGE_KEY, JSON.stringify(state));
}

interface InvestmentOnboardingState extends PersistedOnboarding {
  /** 선택 전략 상품설명/필수 약관 동의 완료 */
  acceptStrategyTerms: (strategyId: string) => void;
  /** SeSAC증권 계좌 연결 — 기존 계좌 연동/신규 계좌 개설 모두 동일하게 사용 */
  connectSesacAccount: (account: SesacAccount) => void;
  /** 입금 — 잔액에 반영하고, 대기 중이던 투자가 있었다면 해소 */
  deposit: (amount: number) => void;
  /** "나중에 입금할게요" — 재로그인 시 입금 요청 화면으로 복귀시키기 위해 저장 */
  deferDeposit: (investment: PendingInvestment) => void;
  clearPendingInvestment: () => void;
}

export const useInvestmentStore = create<InvestmentOnboardingState>((set, get) => {
  const persistCurrent = () => {
    const { termsAcceptedStrategyIds, sesacAccount, pendingInvestment } = get();
    persist({ termsAcceptedStrategyIds, sesacAccount, pendingInvestment });
  };

  return {
    ...loadPersisted(),

    acceptStrategyTerms: (strategyId) => {
      set((s) => ({
        termsAcceptedStrategyIds: s.termsAcceptedStrategyIds.includes(strategyId)
          ? s.termsAcceptedStrategyIds
          : [...s.termsAcceptedStrategyIds, strategyId],
      }));
      persistCurrent();
    },

    connectSesacAccount: (account) => {
      set({ sesacAccount: account });
      persistCurrent();
    },

    deposit: (amount) => {
      set((s) => ({
        sesacAccount: s.sesacAccount ? { ...s.sesacAccount, balance: s.sesacAccount.balance + amount } : s.sesacAccount,
        pendingInvestment: null,
      }));
      persistCurrent();
    },

    deferDeposit: (investment) => {
      set({ pendingInvestment: investment });
      persistCurrent();
    },

    clearPendingInvestment: () => {
      set({ pendingInvestment: null });
      persistCurrent();
    },
  };
});
