import { describe, expect, it } from 'vitest';
import type { StockChartResponse } from './backendApi';
import {
  calculatePeriodChange, formatMarketCap, formatMetric, isChartUnavailable, toChartPoints,
} from './stockDetailModel';

describe('StockDetail actual API view model', () => {
  it('maps Backend chart items without generating synthetic points', () => {
    const chart: StockChartResponse = {
      stock_code: '005930', period: '1W', source: 'KRX', as_of: '2026-08-21T00:00:00Z',
      items: [
        { date: '2026-08-20', open: '70000', high: '71000', low: '69500', close: '70500', volume: 10 },
        { date: '2026-08-21', open: '70500', high: '74000', low: '70400', close: '73800', volume: 20 },
      ],
    };

    const points = toChartPoints(chart);

    expect(points).toEqual([
      { t: '2026-08-20', price: 70500, volume: 10 },
      { t: '2026-08-21', price: 73800, volume: 20 },
    ]);
    expect(calculatePeriodChange(points)).toBeCloseTo(4.68085, 4);
  });

  it('renders missing financial metrics as unavailable', () => {
    expect(formatMetric(null, '배')).toBe('-');
    expect(formatMarketCap(null)).toBe('-');
  });

  it('marks API error and empty response as unavailable', () => {
    expect(isChartUnavailable(true, [])).toBe(true);
    expect(isChartUnavailable(false, [])).toBe(true);
  });
});

