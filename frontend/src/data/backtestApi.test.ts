import { afterEach, describe, expect, it, vi } from 'vitest';
import { API_BASE, runBacktest } from './backtestApi';
import type { BacktestPeriod, BacktestResult } from '../types';

const period: BacktestPeriod = {
  id: 'custom', label: '직접 설정', startDate: '2025-01-01', endDate: '2025-12-31', description: '',
};

const result: BacktestResult = {
  strategyId: 'low',
  strategyName: '저변동성 전략',
  period,
  series: [{ t: '2025-01-02', strategy: 0, benchmark: 0 }],
  metrics: { cumulativeReturn: 1, cagr: 1, mdd: -2, volatility: 3, sharpe: 0.4 },
  benchmarkName: 'KOSPI',
  benchmarkMetrics: { cumulativeReturn: 2, mdd: -3 },
};

afterEach(() => vi.unstubAllGlobals());

describe('runBacktest', () => {
  it('posts the selected strategy and period and returns the real API response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(runBacktest('low', '저변동성 전략', period)).resolves.toEqual(result);
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE}/run`, expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        strategyId: 'low',
        periodId: 'custom',
        periodLabel: '직접 설정',
        periodDescription: '',
        startDate: '2025-01-01',
        endDate: '2025-12-31',
      }),
    }));
  });

  it('surfaces the backend unavailable message without generating fallback results', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ code: 'BACKTEST_DATA_UNAVAILABLE', message: '과거 시세가 부족합니다.' }),
      { status: 404 },
    )));

    await expect(runBacktest('low', '저변동성 전략', period)).rejects.toThrow('과거 시세가 부족합니다.');
  });
});
