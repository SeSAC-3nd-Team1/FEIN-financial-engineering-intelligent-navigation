import type { PortfolioResponse } from './backendApi';
import type { Holding } from '../types';

export type PortfolioHolding = Holding & { stockCode: string };

/** 실제 포지션의 종목코드를 보존해 Mock metadata 존재 여부와 상세 이동을 분리한다. */
export function buildPortfolioHoldings(
  portfolio: PortfolioResponse | null,
): PortfolioHolding[] {
  if (!portfolio) return [];
  return portfolio.positions.map((position) => ({
      stockCode: position.stock_code,
      name: position.stock_name ?? position.stock_code,
      sector: position.sector ?? '-',
      pct: Number(position.weight),
      chg: position.change_rate == null ? null : Number(position.change_rate),
      why: '',
  }));
}
