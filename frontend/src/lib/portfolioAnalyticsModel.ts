import type {
  RebalancingDecisionHistoryResponse,
  RebalancingDecisionResponse,
  StockEvaluationResponse,
} from './backendApi';

export function availableEvaluationAxes(evaluation: StockEvaluationResponse | null) {
  return evaluation?.axes.filter((axis) => axis.status === 'AVAILABLE' && axis.score != null) ?? [];
}

export function formatDecisionReturn(value: string | null | undefined): string {
  if (value == null) return '-';
  const numeric = Number(value);
  return `${numeric >= 0 ? '+' : ''}${numeric.toFixed(2)}%`;
}

export function mergeDecisionHistory(
  history: RebalancingDecisionHistoryResponse | null,
  decision: RebalancingDecisionResponse,
): RebalancingDecisionHistoryResponse {
  const items = [decision, ...(history?.items ?? []).filter((item) => item.id !== decision.id)];
  return {
    account_id: decision.account_id,
    period_label: '최근 6개월',
    proposed: items.length,
    accepted: items.filter((item) => item.decision === 'ACCEPTED').length,
    held: items.filter((item) => item.decision === 'HELD').length,
    items,
  };
}
