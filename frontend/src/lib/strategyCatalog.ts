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
