import type { StockEvaluationResponse } from './backendApi';

export function availableEvaluationAxes(evaluation: StockEvaluationResponse | null) {
  return evaluation?.axes.filter((axis) => axis.status === 'AVAILABLE' && axis.score != null) ?? [];
}

export function formatDecisionReturn(value: string | null | undefined): string {
  if (value == null) return '-';
  const numeric = Number(value);
  return `${numeric >= 0 ? '+' : ''}${numeric.toFixed(2)}%`;
}
