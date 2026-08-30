import type { PortfolioResponse } from './backendApi';
import type { Holding } from '../types';

export type PortfolioHolding = Holding & { stockCode: string };

export function getPositionDisplayName(
  stockCode: string,
  stockName: string | null,
): string {
  return stockName?.trim() || stockCode;
}

export function getPositionSector(sector: string | null): string {
  return sector?.trim() || '-';
}

/** 실제 포지션의 종목코드를 보존해 Mock metadata 존재 여부와 상세 이동을 분리한다. */
export type DetailedPortfolioHolding = PortfolioHolding & {
  principal: number;
  returnRate: number;
};

export function buildDetailedPortfolioHoldings(
  portfolio: PortfolioResponse | null,
): DetailedPortfolioHolding[] {
  if (!portfolio) return [];
  return portfolio.positions.map((position) => ({
    stockCode: position.stock_code,
    name: getPositionDisplayName(position.stock_code, position.stock_name),
    sector: getPositionSector(position.sector),
    pct: Number(position.weight),
    target: undefined,
    chg: position.change_rate == null ? null : Number(position.change_rate),
    principal: Number(position.purchase_amount),
    returnRate: Number(position.return_rate),
    why: '',
  }));
}

export function buildPortfolioHoldings(
  portfolio: PortfolioResponse | null,
): PortfolioHolding[] {
  if (!portfolio) return [];
  return portfolio.positions.map((position) => ({
    stockCode: position.stock_code,
        name: getPositionDisplayName(position.stock_code, position.stock_name),
    sector: getPositionSector(position.sector),
    pct: Number(position.weight),
    target: undefined,
    chg: position.change_rate == null ? null : Number(position.change_rate),
    why: '',
  }));
}
