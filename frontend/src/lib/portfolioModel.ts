import type { PortfolioResponse } from './backendApi';
import type { Holding, StockInfo } from '../types';

export type PortfolioHolding = Holding & { stockCode: string };

/** 실제 포지션의 종목코드를 보존해 Mock metadata 존재 여부와 상세 이동을 분리한다. */
export function buildPortfolioHoldings(
  portfolio: PortfolioResponse | null,
  mockHoldings: Holding[],
  stockInfo: Record<string, StockInfo>,
): PortfolioHolding[] {
  if (!portfolio || portfolio.positions.length === 0) {
    return mockHoldings.map((holding) => ({
      ...holding,
      stockCode: stockInfo[holding.name]?.code ?? '',
    }));
  }

  const assets = Number(portfolio.total_assets);
  return portfolio.positions.map((position) => {
    const matched = mockHoldings.find((holding) => stockInfo[holding.name]?.code === position.stock_code);
    const metadata = matched ?? {
      name: position.stock_code,
      sector: '-',
      pct: 0,
      chg: 0,
      why: '',
    };
    return {
      ...metadata,
      stockCode: position.stock_code,
      name: matched?.name ?? position.stock_code,
      pct: assets > 0 ? Number(position.evaluation_amount) / assets * 100 : 0,
      chg: Number(position.return_rate),
    };
  });
}
