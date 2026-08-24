import { describe, expect, it } from 'vitest';
import { buildPortfolioHoldings } from './portfolioModel';
import type { PortfolioResponse } from './backendApi';

describe('buildPortfolioHoldings', () => {
  it('returns an empty list when no real portfolio is available', () => {
    expect(buildPortfolioHoldings(null)).toEqual([]);
  });

  it('uses actual portfolio metadata without a Mock fallback', () => {
    const portfolio: PortfolioResponse = {
      account_id: 'account',
      cash_balance: '500000',
      total_purchase_amount: '400000',
      total_evaluation_amount: '500000',
      total_assets: '1000000',
      unrealized_profit: '100000',
      realized_profit: '0',
      return_rate: '25',
      today_profit: '1000',
      top_contributor: null,
      contributions: [],
      strategy_targets_available: false,
      rebalancing_proposals: [],
      positions: [{
        stock_code: '123456',
        stock_name: '실제 종목',
        sector: '실제 업종',
        quantity: '1.00000000',
        average_price: '400000',
        current_price: '500000',
        previous_close: '499000',
        change_rate: '0.2',
        purchase_amount: '400000',
        evaluation_amount: '500000',
        unrealized_profit: '100000',
        return_rate: '25',
        realized_profit: '0',
        weight: '50',
        today_profit: '1000',
        price_source: 'KIS',
        price_as_of: '2026-08-25T09:00:00+09:00',
      }],
    };

    const result = buildPortfolioHoldings(portfolio);

    expect(result[0]).toMatchObject({
      stockCode: '123456', name: '실제 종목', sector: '실제 업종', pct: 50, chg: 0.2,
    });

    portfolio.positions[0].change_rate = null;
    expect(buildPortfolioHoldings(portfolio)[0].chg).toBeNull();
  });
});
