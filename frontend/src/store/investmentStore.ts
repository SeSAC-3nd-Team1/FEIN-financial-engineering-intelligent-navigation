import { create } from 'zustand';
import type { OperationMode } from '../data/fees';

export const INVESTMENT_ONBOARDING_STORAGE_PREFIX = 'fein_investment_onboarding';

function storageKey(userId: string): string {
  return `${INVESTMENT_ONBOARDING_STORAGE_PREFIX}:${userId}`;
}

/** MOCK SeSAC증권 연동 계좌 — 실제 증권사 API 연동 전까지 잔액도 프론트 상태로만 관리한다. */
export interface SesacAccount {
  /** 마스킹된 표시용 계좌번호 — 예: "123-****-5678" */
  accountNumber: string;
  /** MOCK 예수금 잔액(원) — 입금 필요 여부 판단에 사용 */
  balance: number;
}

/**
 * 운용방식별 SeSAC증권 계좌 — 같은 계좌로 운용방식을 바꿀 수 없다는 정책에 따라, 운용방식마다
 * 별도의 계좌를 갖는다. 전략은 계좌 안에서 자유롭게 바꿀 수 있어 계좌와 묶이지 않는다.
 */
export type AccountsByMode = Partial<Record<OperationMode, SesacAccount>>;

export interface PendingInvestment {
  strategyId: string;
  strategyName: string;
  amount: number;
  mode: OperationMode;
}

export type InvestmentFlowStep = 'invest-terms' | 'invest-account' | 'invest-deposit' | 'invest-confirm';

/** 투자 시작 Flow(약관~최종확인) 중 어디까지 왔는지 — 새로고침 후 화면/선택값 복원에 사용 */
export interface InFlightInvestment {
  step: InvestmentFlowStep;
  strategyId: string;
  amount: number;
  mode: OperationMode;
}

interface PersistedOnboarding {
  /** 상품설명서·필수 약관 동의를 완료한 전략 id 목록 — 전략마다 상품설명서가 달라 전략 단위로 저장 */
  termsAcceptedStrategyIds: string[];
  accountsByMode: AccountsByMode;
  /** "나중에 입금할게요"로 대기 중인 투자 — null이면 대기 중인 입금 없음 */
  pendingInvestment: PendingInvestment | null;
  inFlight: InFlightInvestment | null;
  /**
   * 실제 투자가 시작된(ensureAccount 성공) 운용방식 — Portfolio/Dashboard가 "지금 어떤 방식으로
   * 운용 중인지" 판단하는 데 쓴다. 백엔드 계좌 모델에 아직 운용방식 필드가 없어 프론트에서만
   * 별도로 추적하는 값이며, 추후 계좌 API에 operating_mode가 추가되면 그쪽 값으로 교체하면 된다.
   */
  activeMode: OperationMode | null;
}

const EMPTY_ONBOARDING: PersistedOnboarding = {
  termsAcceptedStrategyIds: [],
  accountsByMode: {},
  pendingInvestment: null,
  inFlight: null,
  activeMode: null,
};

/** userId가 없으면(비로그인) 저장할 곳이 없으니 빈 상태를 돌려준다 — 이 상태는 persist 대상도 아니다 */
function loadPersisted(userId: string | null): PersistedOnboarding {
  if (!userId) return EMPTY_ONBOARDING;
  try {
    const raw = localStorage.getItem(storageKey(userId));
    if (!raw) return EMPTY_ONBOARDING;
    return { ...EMPTY_ONBOARDING, ...JSON.parse(raw) };
  } catch {
    return EMPTY_ONBOARDING;
  }
}

function persist(userId: string | null, state: PersistedOnboarding) {
  if (!userId) return;
  localStorage.setItem(storageKey(userId), JSON.stringify(state));
}

interface InvestmentOnboardingState extends PersistedOnboarding {
  /** 현재 이 상태가 어느 사용자 것인지 — localStorage 키를 사용자별로 분리하기 위함 (persist 대상 아님) */
  currentUserId: string | null;
  /** 로그인/로그아웃 시 호출 — 해당 사용자(또는 비로그인=null)의 저장된 상태로 교체한다 */
  hydrateForUser: (userId: string | null) => void;
  /** 선택 전략 상품설명/필수 약관 동의 완료 */
  acceptStrategyTerms: (strategyId: string) => void;
  /** 특정 운용방식의 SeSAC증권 계좌 연결 — 기존 계좌 연동/신규 계좌 개설 모두 동일하게 사용 */
  connectSesacAccount: (mode: OperationMode, account: SesacAccount) => void;
  /** 특정 운용방식 계좌에 입금 — 잔액에 반영하고, 대기 중이던 투자가 있었다면 해소 */
  deposit: (mode: OperationMode, amount: number) => void;
  /** "나중에 입금할게요" — 재로그인 시 입금 요청 화면으로 복귀시키기 위해 저장 */
  deferDeposit: (investment: PendingInvestment) => void;
  clearPendingInvestment: () => void;
  /** invest-terms~invest-confirm 중 한 화면에 진입/이동할 때마다 호출 — 새로고침 복원용 */
  setInFlightStep: (step: InFlightInvestment) => void;
  /** Flow를 벗어나거나(뒤로가기로 금액 선택 화면 등) 완료했을 때 호출 */
  clearInFlight: () => void;
  /** 실제 투자 시작(ensureAccount 성공) 시점에 호출 — 현재 활성 운용방식을 기록 */
  setActiveMode: (mode: OperationMode) => void;
}

export const useInvestmentStore = create<InvestmentOnboardingState>((set, get) => {
  const persistCurrent = () => {
    const { currentUserId, termsAcceptedStrategyIds, accountsByMode, pendingInvestment, inFlight, activeMode } = get();
    persist(currentUserId, { termsAcceptedStrategyIds, accountsByMode, pendingInvestment, inFlight, activeMode });
  };

  return {
    currentUserId: null,
    ...EMPTY_ONBOARDING,

    hydrateForUser: (userId) => {
      set({ currentUserId: userId, ...loadPersisted(userId) });
    },

    acceptStrategyTerms: (strategyId) => {
      set((s) => ({
        termsAcceptedStrategyIds: s.termsAcceptedStrategyIds.includes(strategyId)
          ? s.termsAcceptedStrategyIds
          : [...s.termsAcceptedStrategyIds, strategyId],
      }));
      persistCurrent();
    },

    connectSesacAccount: (mode, account) => {
      set((s) => ({ accountsByMode: { ...s.accountsByMode, [mode]: account } }));
      persistCurrent();
    },

    deposit: (mode, amount) => {
      set((s) => {
        const account = s.accountsByMode[mode];
        if (!account) return s;
        return { accountsByMode: { ...s.accountsByMode, [mode]: { ...account, balance: account.balance + amount } } };
      });
      set({ pendingInvestment: null });
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

    setInFlightStep: (inFlight) => {
      set({ inFlight });
      persistCurrent();
    },

    clearInFlight: () => {
      set({ inFlight: null });
      persistCurrent();
    },

    setActiveMode: (mode) => {
      set({ activeMode: mode });
      persistCurrent();
    },
  };
});
