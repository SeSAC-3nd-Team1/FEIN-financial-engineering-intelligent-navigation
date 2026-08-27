import type { StrategyResponse } from './backendApi';

const RISK_LABEL: Record<string, string> = { LOW: '낮음', MEDIUM: '보통', HIGH: '높음' };
const REBALANCE_LABEL: Record<string, string> = {
  WEEKLY: '주 1회', MONTHLY: '월 1회', QUARTERLY: '분기 1회', YEARLY: '연 1회',
};

/** Backend 전략 카탈로그 enum을 사용자 표시 문구로 변환한다. 알 수 없는 신규 값은 숨기지 않는다. */
export function strategyRiskLabel(riskLevel: string): string {
  return RISK_LABEL[riskLevel] ?? riskLevel;
}

export function strategyRebalanceLabel(rebalanceCycle: string): string {
  return REBALANCE_LABEL[rebalanceCycle] ?? rebalanceCycle;
}

/**
 * 포트폴리오 화면에서는 탐색 중 선택한 strategyId보다 실제 계좌의 selected_strategy_id를 우선한다.
 * accountSelectedStrategyId가 undefined면 계좌 조회 전 상태이므로 기존 navigationStrategy로 먼저 렌더링하고,
 * 실제 계좌가 로드된 뒤에는 null/불일치까지 포함해 계좌 상태를 그대로 Source of Truth로 사용한다.
 */
export function resolvePortfolioStrategy(
  catalog: StrategyResponse[],
  navigationStrategy: StrategyResponse | null,
  accountSelectedStrategyId: string | null | undefined,
): StrategyResponse | null {
  if (accountSelectedStrategyId === undefined) return navigationStrategy;
  if (accountSelectedStrategyId === null) return null;
  return catalog.find((item) => item.id === accountSelectedStrategyId) ?? null;
}
