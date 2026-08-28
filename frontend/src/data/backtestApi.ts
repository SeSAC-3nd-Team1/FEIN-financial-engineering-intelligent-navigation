import { getMockBacktestResult, MOCK_AVAILABLE_RANGE } from './mockBacktest';
import type {
  BacktestAiContext,
  BacktestAiExplanation,
  BacktestPeriod,
  BacktestResult,
} from '../types';

export const API_BASE = '/api/v1/backtest';

/**
 * 실제 백테스트 모델/KRX 데이터 연동 전까지, Frontend 개발·UX 검증용으로만 쓰는 명시적 Mock 모드.
 * 절대 API 오류(404/422/500) 발생 시 자동으로 켜지는 fallback이 아니다 — .env에서 명시적으로
 * VITE_USE_MOCK_BACKTEST=true를 켰을 때만 동작하고, 꺼져 있으면(기본값) 항상 실제 API를 호출해
 * 기존 에러 처리(404/422 등)가 그대로 유지된다.
 */
export const USE_MOCK_BACKTEST = import.meta.env.VITE_USE_MOCK_BACKTEST === 'true';

if (import.meta.env.PROD && USE_MOCK_BACKTEST) {
  throw new Error('Mock backtest is disabled in production.');
}

export interface BacktestAvailableRange {
  minDate: string;
  maxDate: string;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { headers: { Accept: 'application/json' } });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { message?: string } | null;
    throw new Error(payload?.message ?? `서버가 ${response.status} 응답을 보냈어요. 잠시 후 다시 시도해주세요.`);
  }
  return await response.json() as T;
}

async function request<T>(path: string, body: unknown): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 15_000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null) as { message?: string } | null;
      throw new Error(payload?.message ?? `서버가 ${response.status} 응답을 보냈어요. 잠시 후 다시 시도해주세요.`);
    }
    return await response.json() as T;
  } finally {
    clearTimeout(timer);
  }
}

export function runBacktest(
  strategyId: string,
  strategyName: string,
  period: BacktestPeriod,
): Promise<BacktestResult> {
  if (USE_MOCK_BACKTEST) return getMockBacktestResult(strategyId, strategyName, period);
  return request<BacktestResult>('/run', {
    strategyId,
    periodId: period.id,
    periodLabel: period.label,
    periodDescription: period.description,
    startDate: period.startDate,
    endDate: period.endDate,
  });
}

export function getBacktestAvailableRange(): Promise<BacktestAvailableRange> {
  if (USE_MOCK_BACKTEST) return Promise.resolve(MOCK_AVAILABLE_RANGE);
  return get<BacktestAvailableRange>('/available-range');
}

const fmtShort = (iso: string) => `${iso.slice(0, 4)}.${iso.slice(5, 7)}`;

function periodOpening(ctx: BacktestAiContext): string {
  if (ctx.periodType === 'custom') {
    return `선택한 ${fmtShort(ctx.startDate)}~${fmtShort(ctx.endDate)} 기간에는`;
  }
  return `${ctx.periodLabel} 기간에는`;
}

/** 실제 백테스트 숫자만 문장으로 옮기는 로컬 설명이며 별도 AI 점수를 생성하지 않는다. */
export function fetchAiExplanation(ctx: BacktestAiContext): Promise<BacktestAiExplanation> {
  const opening = periodOpening(ctx);
  const difference = Math.round((ctx.cumulativeReturn - ctx.benchmarkReturn) * 10) / 10;
  const headline = difference > 0
    ? `${ctx.benchmarkName}보다 ${Math.abs(difference)}%p 높은 성과였어요`
    : difference < 0
      ? `${ctx.benchmarkName}보다 ${Math.abs(difference)}%p 낮은 성과였어요`
      : `${ctx.benchmarkName}과 같은 누적 수익률이었어요`;
  const comparison = difference >= 0
    ? `${ctx.benchmarkName}보다 ${Math.abs(difference)}%p 높았어요.`
    : `${ctx.benchmarkName}보다 ${Math.abs(difference)}%p 낮았어요.`;
  const sharpe = ctx.sharpe == null ? '' : ` 샤프 지수는 ${ctx.sharpe}였어요.`;
  return Promise.resolve({
    headline,
    overview: `${opening} ${ctx.strategyName}은 누적 ${ctx.cumulativeReturn}%를 기록했고, ${comparison}`,
    caution: `이 기간 최대 낙폭은 ${ctx.mdd}%, 연환산 변동성은 ${ctx.volatility}%였어요.${sharpe}`,
    generatedAt: new Date().toISOString(),
  });
}
