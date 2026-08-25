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
  /**
   * 이 계좌가 지금 운용 중인 전략(STRATEGIES의 id) — "계좌 1개 = 활성 전략 1개" 정책의 핵심 필드.
   * 실제 투자 시작(ensureAccount 성공) 또는 전략 변경(같은 계좌 내에서만 가능) 시점에만 갱신되고,
   * null이면 계좌는 있지만 아직 투자가 시작되지 않은 상태다.
   */
  activeStrategyId: string | null;
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
  /**
   * DEPOSIT_PENDING(계좌 준비는 끝났지만 아직 투자가 시작되지 않은) 상태의 투자 — null이면 해당 없음.
   * "나중에 입금할게요" 버튼뿐 아니라, 계좌 준비가 끝나 invest-deposit/invest-confirm 단계에 들어서는
   * 순간부터 자동으로 세팅된다(App.tsx의 enterInvestmentStep 참고). 실제 투자가 시작(최종 확인 성공)
   * 되기 전까지는 입금 여부와 무관하게 유지되고, clearPendingInvestment는 그 성공 시점에만 호출한다.
   */
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

/** 이 변경(운용방식별 계좌) 이전에 저장된 단일 계좌 필드 — 마이그레이션 판단에만 쓰고 새 상태에는 남기지 않는다 */
interface LegacyPersistedOnboardingV1 {
  sesacAccount?: SesacAccount | null;
}

/** userId가 없으면(비로그인) 저장할 곳이 없으니 빈 상태를 돌려준다 — 이 상태는 persist 대상도 아니다 */
function loadPersisted(userId: string | null): PersistedOnboarding {
  if (!userId) return EMPTY_ONBOARDING;
  try {
    const raw = localStorage.getItem(storageKey(userId));
    if (!raw) return EMPTY_ONBOARDING;
    const parsed = JSON.parse(raw) as Partial<PersistedOnboarding> & LegacyPersistedOnboardingV1;
    const merged: PersistedOnboarding = { ...EMPTY_ONBOARDING, ...parsed, accountsByMode: parsed.accountsByMode ?? {} };

    // 이 변경 전에는 sesacAccount 하나만 저장했다 — 그 계좌가 어느 운용방식이었는지는 저장돼 있지
    // 않으므로, pendingInvestment/inFlight에 남은 mode를 우선 쓰고 없으면 이 변경 전 기본값이던
    // 'manual'로 간주한다. 마이그레이션하지 않으면 invest-deposit 등에서 해당 mode의 계좌를 찾지
    // 못해 화면이 비어 보이는 문제가 생긴다.
    if (parsed.sesacAccount && Object.keys(merged.accountsByMode).length === 0) {
      const inferredMode: OperationMode = parsed.pendingInvestment?.mode ?? parsed.inFlight?.mode ?? 'manual';
      merged.accountsByMode = { [inferredMode]: parsed.sesacAccount };
    }

    // 이 변경(계좌당 activeStrategyId) 이전에 저장된 계좌는 이 필드가 없다 — 없으면 "아직 활성 전략
    // 없음"으로 간주한다. 실제로 이미 투자 중이던 이전 상태라면 최초 1회 "이 전략으로 시작하기"가
    // 다시 보일 수 있지만, 이 필드가 추가되기 전에는 어떤 전략이 활성이었는지 저장돼 있지 않아 안전한
    // 기본값(null)으로만 채운다.
    merged.accountsByMode = Object.fromEntries(
      (Object.entries(merged.accountsByMode) as [OperationMode, SesacAccount][]).map(([mode, account]) => [
        mode,
        { ...account, activeStrategyId: account.activeStrategyId ?? null },
      ]),
    ) as AccountsByMode;

    return merged;
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
  /**
   * DEPOSIT_PENDING 상태를 기록 — 재로그인/Portfolio 진입 시 입금 요청 화면으로 복귀시키기 위해 저장.
   * "나중에 입금할게요" 버튼 클릭 시뿐 아니라 계좌 준비 완료 시점에도 App.tsx에서 호출된다.
   */
  deferDeposit: (investment: PendingInvestment) => void;
  clearPendingInvestment: () => void;
  /** invest-terms~invest-confirm 중 한 화면에 진입/이동할 때마다 호출 — 새로고침 복원용 */
  setInFlightStep: (step: InFlightInvestment) => void;
  /** Flow를 벗어나거나(뒤로가기로 금액 선택 화면 등) 완료했을 때 호출 */
  clearInFlight: () => void;
  /** 실제 투자 시작(ensureAccount 성공) 시점에 호출 — 현재 활성 운용방식을 기록 */
  setActiveMode: (mode: OperationMode) => void;
  /**
   * "계좌 1개 = 활성 전략 1개" 정책의 실제 반영 지점 — 신규 투자 시작(ensureAccount 성공) 시점과,
   * 같은 계좌 안에서 전략을 변경(StrategyDetail "이 전략으로 변경하기" 확인)할 때 모두 이 액션 하나로
   * 처리한다. 배열이 아니라 단일 필드를 덮어쓰는 구조라 한 계좌에 두 전략이 동시에 활성화되는 상태
   * 자체가 나올 수 없다. 해당 mode에 계좌가 없으면(비정상 호출) 아무것도 하지 않는다.
   */
  setAccountActiveStrategy: (mode: OperationMode, strategyId: string) => void;
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
      set((s) => {
        // 최종 방어선 — "같은 계좌로는 운용방식을 바꿀 수 없다"는 정책은 UI(InvestAccount)에서도
        // 막지만, 화면 쪽 경로 하나를 놓치더라도 스토어에서 다른 운용방식과 계좌번호가 겹치는
        // 저장 자체를 거부해 정책이 깨지지 않게 한다.
        const usedByOtherMode = (Object.entries(s.accountsByMode) as [OperationMode, SesacAccount][])
          .some(([m, acc]) => m !== mode && acc.accountNumber === account.accountNumber);
        if (usedByOtherMode) {
          console.warn(`[investmentStore] ${account.accountNumber}는 이미 다른 운용방식에 연결된 계좌라 ${mode}에 연결하지 않았습니다.`);
          return s;
        }
        return { accountsByMode: { ...s.accountsByMode, [mode]: account } };
      });
      persistCurrent();
    },

    deposit: (mode, amount) => {
      // 입금은 DEPOSIT_PENDING을 해소하지 않는다 — 최종 확인(투자 시작)까지 남아있어야 이 사이에
      // 이탈해도 입금 단계부터 이어갈 수 있다. clearPendingInvestment는 투자 시작 성공 시에만 호출한다.
      set((s) => {
        const account = s.accountsByMode[mode];
        if (!account) return s;
        return { accountsByMode: { ...s.accountsByMode, [mode]: { ...account, balance: account.balance + amount } } };
      });
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

    setAccountActiveStrategy: (mode, strategyId) => {
      set((s) => {
        const account = s.accountsByMode[mode];
        if (!account) {
          console.warn(`[investmentStore] ${mode} 계좌가 없어 activeStrategy를 설정하지 않았습니다.`);
          return s;
        }
        return { accountsByMode: { ...s.accountsByMode, [mode]: { ...account, activeStrategyId: strategyId } } };
      });
      persistCurrent();
    },
  };
});
