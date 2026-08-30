import { ALL_HOLDINGS, STOCK_INFO } from '../data/holdings';
import type {
  PortfolioContributionResponse,
  PortfolioHistoryPeriod,
  PortfolioHistoryResponse,
  StockEvaluationResponse,
} from './backendApi';

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
  return {
    items: (history?.items ?? []).map((item) => ({
      label: item.date,
      port: Number(item.portfolio_return_rate),
      kospi: item.benchmark_return_rate == null ? null : Number(item.benchmark_return_rate),
    })),
    usesMock: false,
  };
}

export function hybridContributionData(real: PortfolioContributionResponse[]) {
  return {
    items: real.map((item) => ({
      name: item.stock_name ?? item.stock_code,
      amount: Number(item.amount),
    })).sort((a, b) => b.amount - a.amount),
    usesMock: false,
  };
}

export function hybridEvaluation(
  evaluation: StockEvaluationResponse | null,
  stockCode: string,
) {
  return {
    axes: evaluation?.axes ?? [],
    roleSummary: evaluation?.role_summary ?? null,
    usesMock: false,
  };
}
