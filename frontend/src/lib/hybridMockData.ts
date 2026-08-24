import { AI_AXES, ALL_HOLDINGS, PORTFOLIO_TREND, STOCK_CONTRIBUTION, STOCK_INFO } from '../data/holdings';
import type {
  PortfolioContributionResponse,
  PortfolioHistoryPeriod,
  PortfolioHistoryResponse,
  StockEvaluationAxisResponse,
  StockEvaluationResponse,
} from './backendApi';

const EVALUATION_KEYS: StockEvaluationAxisResponse['key'][] = [
  'stability', 'financial_health', 'growth', 'defense', 'diversification',
];

export function mockStockByCode(stockCode: string) {
  const entry = Object.entries(STOCK_INFO).find(([, info]) => info.code === stockCode);
  if (!entry) return null;
  const [name, info] = entry;
  const holding = ALL_HOLDINGS.find((item) => item.name === name) ?? null;
  return { name, info, holding };
}

export function hybridTrendData(
  history: PortfolioHistoryResponse | null,
  period: PortfolioHistoryPeriod,
) {
  if (history?.items.length) {
    return {
      items: history.items.map((item) => ({
        label: item.date,
        port: Number(item.portfolio_return_rate),
        kospi: item.benchmark_return_rate == null ? null : Number(item.benchmark_return_rate),
      })),
      usesMock: false,
    };
  }
  const counts: Record<PortfolioHistoryPeriod, number> = { '1M': 2, '3M': 4, '1Y': 12, ALL: 12 };
  return { items: PORTFOLIO_TREND.slice(-counts[period]), usesMock: true };
}

export function hybridContributionData(real: PortfolioContributionResponse[]) {
  if (real.length) {
    return {
      items: real.map((item) => ({
        name: item.stock_name ?? item.stock_code,
        amount: Number(item.amount),
      })).sort((a, b) => b.amount - a.amount),
      usesMock: false,
    };
  }
  return { items: STOCK_CONTRIBUTION, usesMock: true };
}

export function hybridEvaluation(
  evaluation: StockEvaluationResponse | null,
  stockCode: string,
) {
  const fallback = mockStockByCode(stockCode);
  if (!fallback) {
    return {
      axes: evaluation?.axes ?? [],
      roleSummary: evaluation?.role_summary ?? null,
      usesMock: false,
    };
  }
  const byKey = new Map((evaluation?.axes ?? []).map((axis) => [axis.key, axis]));
  let usesMock = false;
  const axes = EVALUATION_KEYS.map((key, index): StockEvaluationAxisResponse => {
    const real = byKey.get(key);
    if (real?.score != null) return real;
    usesMock = true;
    return {
      key,
      label: real?.label ?? AI_AXES[index],
      score: fallback.info.ai[index],
      status: 'AVAILABLE',
      basis: '실제 데이터 연동 전 기존 데모 점수입니다.',
    };
  });
  return {
    axes,
    roleSummary: evaluation?.role_summary ?? fallback.holding?.why ?? null,
    usesMock,
  };
}
