import type { PortfolioResponse } from './backendApi';
import type { Holding } from '../types';
import { mockStockByCode } from './hybridMockData';

export type PortfolioHolding = Holding & { stockCode: string };

/** 실제 포지션의 종목코드를 보존해 Mock metadata 존재 여부와 상세 이동을 분리한다. */
export function buildPortfolioHoldings(
  portfolio: PortfolioResponse | null,
): PortfolioHolding[] {
  if (!portfolio) return [];
  return portfolio.positions.map((position) => {
    const fallback = mockStockByCode(position.stock_code);
    return {
      stockCode: position.stock_code,
      name: position.stock_name ?? fallback?.name ?? position.stock_code,
      sector: position.sector ?? fallback?.holding?.sector ?? '-',
      pct: Number(position.weight),
      target: fallback?.holding?.target ?? fallback?.holding?.pct,
      chg: position.change_rate == null ? fallback?.holding?.chg ?? null : Number(position.change_rate),
      why: fallback?.holding?.why ?? '',
    };
  });
}
