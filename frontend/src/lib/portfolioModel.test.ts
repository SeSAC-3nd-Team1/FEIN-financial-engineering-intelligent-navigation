import { describe, expect, it } from 'vitest';
import { buildPortfolioHoldings } from './portfolioModel';
import type { PortfolioResponse } from './backendApi';

describe('buildPortfolioHoldings', () => {
  it('preserves an actual position code even when Mock metadata does not contain it', () => {
    const portfolio: PortfolioResponse = {
      account_id: 'account',
      cash_balance: '500000',
      total_purchase_amount: '400000',
      total_evaluation_amount: '500000',
      total_assets: '1000000',
      unrealized_profit: '100000',
      realized_profit: '0',
      return_rate: '25',
      positions: [{
        stock_code: '123456',
        quantity: 1,
        average_price: '400000',
        current_price: '500000',
        purchase_amount: '400000',
        evaluation_amount: '500000',
        unrealized_profit: '100000',
        return_rate: '25',
        realized_profit: '0',
      }],
    };

    const result = buildPortfolioHoldings(portfolio, [], {});

    expect(result[0]).toMatchObject({ stockCode: '123456', name: '123456', pct: 50 });
  });
});
