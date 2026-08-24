import type { SesacAccount } from '../store/investmentStore';

export type InvestmentEntryStep = 'invest-terms' | 'invest-account' | 'invest-deposit' | 'invest-confirm';

export interface InvestmentEntryInput {
  strategyId: string;
  /** 투자 예정 금액 — 잔액과 비교해 입금 단계 필요 여부를 판단 */
  amount: number;
  termsAcceptedStrategyIds: string[];
  sesacAccount: SesacAccount | null;
}

const STEP_ORDER: InvestmentEntryStep[] = ['invest-terms', 'invest-account', 'invest-deposit', 'invest-confirm'];

/** 해당 단계가 현재 상태 기준으로 아직 필요한지 — invest-confirm은 다른 단계가 다 끝난 뒤 항상 마지막에 보여준다 */
function isStepRequired(step: InvestmentEntryStep, input: InvestmentEntryInput): boolean {
  const { strategyId, amount, termsAcceptedStrategyIds, sesacAccount } = input;
  switch (step) {
    case 'invest-terms': return !termsAcceptedStrategyIds.includes(strategyId);
    case 'invest-account': return !sesacAccount;
    case 'invest-deposit': return !sesacAccount || sesacAccount.balance < amount;
    case 'invest-confirm': return true;
  }
}

/**
 * "이 전략으로 시작하기" 클릭 시(또는 대기 중인 투자 복귀 시) 다음으로 필요한 단계를 결정한다.
 * 이미 완료한 단계는 건너뛴다. 투자성향 유효성은 이 함수 호출 이전에 기존 investor-check/risk
 * 가드에서 이미 보장되므로 여기서는 다루지 않는다.
 */
export function resolveInvestmentEntryStep(input: InvestmentEntryInput): InvestmentEntryStep {
  return STEP_ORDER.find((step) => isStepRequired(step, input)) ?? 'invest-confirm';
}

/**
 * 투자 Flow 화면의 "이전으로" — 화면 순서상 바로 앞 단계로 고정 이동하지 않고, 현재 상태 기준으로
 * 아직 필요한 가장 가까운 이전 단계로 돌아간다. 예를 들어 약관 동의가 이미 끝난 상태로
 * invest-account에 있다면 "이전으로"는 invest-terms(이미 완료됨)를 건너뛰고 금액 선택
 * 화면('start')으로 나간다 — "이미 완료한 단계는 다시 요구하지 않는다" 원칙을 뒤로가기에도 적용한다.
 */
export function resolvePreviousStep(currentStep: InvestmentEntryStep, input: InvestmentEntryInput): InvestmentEntryStep | 'start' {
  const idx = STEP_ORDER.indexOf(currentStep);
  for (let i = idx - 1; i >= 0; i--) {
    if (isStepRequired(STEP_ORDER[i], input)) return STEP_ORDER[i];
  }
  return 'start';
}
