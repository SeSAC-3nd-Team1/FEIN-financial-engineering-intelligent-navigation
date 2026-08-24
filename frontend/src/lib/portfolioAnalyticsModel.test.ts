import { describe, expect, it } from 'vitest';
import { availableEvaluationAxes, formatDecisionReturn, mergeDecisionHistory } from './portfolioAnalyticsModel';
import type { RebalancingDecisionResponse, StockEvaluationResponse } from './backendApi';

describe('portfolio analytics model', () => {
  it('keeps unavailable feature axes out of the radar series', () => {
    const evaluation = {
      axes: [
        { key: 'stability', label: '안정성', score: 72, status: 'AVAILABLE', basis: 'KRX' },
        { key: 'growth', label: '성장성', score: null, status: 'UNAVAILABLE', basis: '재무 부족' },
      ],
    } as StockEvaluationResponse;

    expect(availableEvaluationAxes(evaluation)).toEqual([evaluation.axes[0]]);
  });

  it('formats only real recorded returns and preserves unavailable', () => {
    expect(formatDecisionReturn('1.234')).toBe('+1.23%');
    expect(formatDecisionReturn('-0.5')).toBe('-0.50%');
    expect(formatDecisionReturn(null)).toBe('-');
  });

  it('applies a successful POST response without a fallible history refresh', () => {
    const decision = {
      id: 'decision-1', account_id: 'account-1', decision: 'ACCEPTED',
    } as RebalancingDecisionResponse;

    const history = mergeDecisionHistory(null, decision);
    const retried = mergeDecisionHistory(history, decision);

    expect(retried.items).toEqual([decision]);
    expect(retried).toMatchObject({ proposed: 1, accepted: 1, held: 0 });
  });
});
