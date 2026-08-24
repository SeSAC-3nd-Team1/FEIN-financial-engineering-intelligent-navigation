import type { StockChartResponse } from './backendApi';

export interface StockChartPoint {
  t: string;
  price: number;
  volume: number;
}

export const numeric = (value: string | null | undefined) => value == null ? null : Number(value);

export const signed = (value: number | null, digits = 2) => value == null || !Number.isFinite(value)
  ? '-'
  : `${value > 0 ? '+' : ''}${value.toFixed(digits)}`;

export const formatMetric = (value: string | null, suffix: string) => {
  const number = numeric(value);
  return number == null || !Number.isFinite(number) ? '-' : `${number.toFixed(2)}${suffix}`;
};

export const formatMarketCap = (value: string | null) => {
  const number = numeric(value);
  if (number == null || !Number.isFinite(number)) return '-';
  if (number >= 1_000_000_000_000) return `${(number / 1_000_000_000_000).toFixed(1)}조원`;
  return `${Math.round(number / 100_000_000).toLocaleString('ko-KR')}억원`;
};

export const toChartPoints = (chart: StockChartResponse | null): StockChartPoint[] =>
  (chart?.items ?? []).map((item) => ({
    t: item.date,
    price: Number(item.close),
    volume: item.volume,
  })).filter((item) => Number.isFinite(item.price));

export const calculatePeriodChange = (points: StockChartPoint[]) => {
  if (points.length < 2 || points[0].price <= 0) return null;
  return (points[points.length - 1].price / points[0].price - 1) * 100;
};

export const isChartUnavailable = (chartError: boolean, points: StockChartPoint[]) =>
  chartError || points.length === 0;

