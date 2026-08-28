import { describe, expect, it } from 'vitest';
import type { PortfolioHistoryResponse, StockEvaluationResponse } from './backendApi';
import { hybridContributionData, hybridEvaluation, hybridTrendData, mockStockByCode } from './hybridMockData';

describe('hybrid Mock fallback', () => {
  it('uses actual portfolio history whenever at least one snapshot exists', () => {
    const history: PortfolioHistoryResponse = {
      account_id: 'account',
      period: '1M',
      benchmark_name: 'KOSPI',
      items: [{
        date: '2026-08-25',
        total_assets: '1000000',
        portfolio_return_rate: '1.25',
        benchmark_return_rate: '0.5',
      }],
    };

    expect(hybridTrendData(history, '1M')).toEqual({
      items: [{ label: '2026-08-25', port: 1.25, kospi: 0.5 }],
      usesMock: false,
    });
  });

  it('shows an empty trend when the API has no snapshots', () => {
    const result = hybridTrendData(null, '3M');
    expect(result).toEqual({ items: [], usesMock: false });
  });

  it('keeps actual contribution data ahead of the Mock fallback', () => {
    const result = hybridContributionData([{
      stock_code: '005930',
      stock_name: '실제 삼성전자',
      amount: '1234',
      share_rate: '50',
    }]);
    expect(result).toEqual({
      items: [{ name: '실제 삼성전자', amount: 1234 }],
      usesMock: false,
    });
  });

  it('fills only unavailable evaluation axes and preserves an actual zero score', () => {
    const evaluation: StockEvaluationResponse = {
      account_id: 'account',
      stock_code: '005930',
      stock_name: '삼성전자',
      feature_version: 'stock-feature-v1',
      as_of: '2026-08-25',
      target_weight: null,
      role_summary: '실제 역할 설명',
      axes: [{
        key: 'stability',
        label: '실제 안정성',
        score: 0,
        status: 'AVAILABLE',
        basis: '실제 데이터',
      }],
      sources: ['KRX'],
    };

    const result = hybridEvaluation(evaluation, '005930');
    expect(result.axes[0]).toEqual(evaluation.axes[0]);
    expect(result.axes).toEqual(evaluation.axes);
    expect(result.roleSummary).toBe('실제 역할 설명');
    expect(result.usesMock).toBe(false);
  });

  it('finds the original Mock metadata by stock code', () => {
    expect(mockStockByCode('005930')?.name).toBe('삼성전자');
    expect(mockStockByCode('999999')).toBeNull();
  });
});
