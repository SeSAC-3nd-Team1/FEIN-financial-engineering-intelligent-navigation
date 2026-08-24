import { describe, expect, it } from 'vitest';
import { availableEvaluationAxes, formatDecisionReturn } from './portfolioAnalyticsModel';
import type { StockEvaluationResponse } from './backendApi';

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
});
