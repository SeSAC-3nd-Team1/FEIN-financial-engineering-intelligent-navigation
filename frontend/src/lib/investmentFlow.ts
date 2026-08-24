import type { SesacAccount } from '../store/investmentStore';

export type InvestmentEntryStep = 'invest-terms' | 'invest-account' | 'invest-deposit' | 'invest-confirm';

export interface InvestmentEntryInput {
  strategyId: string;
  /** 투자 예정 금액 — 잔액과 비교해 입금 단계 필요 여부를 판단 */
  amount: number;
  termsAcceptedStrategyIds: string[];
  sesacAccount: SesacAccount | null;
}

/**
 * "이 전략으로 시작하기" 클릭 시(또는 대기 중인 투자 복귀 시) 다음으로 필요한 단계를 결정한다.
 * 이미 완료한 단계는 건너뛴다. 투자성향 유효성은 이 함수 호출 이전에 기존 investor-check/risk
 * 가드에서 이미 보장되므로 여기서는 다루지 않는다.
 */
export function resolveInvestmentEntryStep(input: InvestmentEntryInput): InvestmentEntryStep {
  const { strategyId, amount, termsAcceptedStrategyIds, sesacAccount } = input;
  if (!termsAcceptedStrategyIds.includes(strategyId)) return 'invest-terms';
  if (!sesacAccount) return 'invest-account';
  if (sesacAccount.balance < amount) return 'invest-deposit';
  return 'invest-confirm';
}
