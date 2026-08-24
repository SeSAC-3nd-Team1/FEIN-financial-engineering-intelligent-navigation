import { describe, expect, it } from 'vitest';
import { getRecommendedPeriods, validateCustomPeriod } from './backtestPeriods';

describe('backtest periods', () => {
  const range = { minDate: '2022-09-18', maxDate: '2026-08-24' };

  it('only recommends periods contained in the backend range', () => {
    const periods = getRecommendedPeriods(range);

    expect(periods.map((period) => period.id)).toEqual(['recent-5y']);
    expect(periods[0]).toMatchObject({ startDate: range.minDate, endDate: range.maxDate });
  });

  it('validates custom periods against the backend range', () => {
    expect(validateCustomPeriod('2022-01-01', '2023-01-01', range)).toContain('데이터가 없어요');
    expect(validateCustomPeriod('2023-01-01', '2027-01-01', range)).toContain('데이터가 없어요');
    expect(validateCustomPeriod('2023-01-01', '2024-01-01', range)).toBeNull();
  });
});
