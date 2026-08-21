import type {
  BacktestAiContext,
  BacktestAiExplanation,
  BacktestMetrics,
  BacktestPeriod,
  BacktestResult,
  BacktestSeriesPoint,
} from '../types';

/* ============================================================
 * Backtest 외부 API 계약 (실 연동 전까지 USE_MOCK=true)
 *
 *  POST {API_BASE}/run    { strategyId, periodId, startDate, endDate } → BacktestResult
 *  POST {API_BASE}/explain BacktestAiContext                          → BacktestAiExplanation
 * ============================================================ */
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'https://api.example.com/v1/backtest';

/** true 인 동안 목 데이터를 쓴다. 실 연동 시 false */
export const USE_MOCK = true;

async function request<T>(path: string, body: unknown): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 8000);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`서버가 ${res.status} 응답을 보냈어요. 잠시 후 다시 시도해주세요.`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

const delay = <T,>(v: T, ms = 700) => new Promise<T>((r) => setTimeout(() => r(v), ms));

/* ----- MOCK 백테스트 엔진 -----
 * 실제 시세 데이터가 아니라, 전략·기간을 시드로 쓰는 결정적 합성 곡선이다
 * (StockDetail.tsx 의 priceSeries 와 동일한 LCG 기법). 지표는 손으로 지어낸
 * 값이 아니라 이 합성 곡선에서 매번 계산해서 얻는다 — 실 엔진 연동 시
 * runBacktest 내부만 실제 fetch 로 바꾸면 나머지 로직은 그대로 쓸 수 있다.
 */

// vol 은 연환산 시 STRATEGIES(data/strategies.ts)의 low/value/momentum 변동성(12.4%/15.8%/21.3%)과
// 비슷한 자릿수가 나오도록 맞춘 계수 — 실제 시세가 아니므로 정확히 일치할 필요는 없다.
const STRATEGY_RISK: Record<string, { vol: number; benchmarkVolMultiplier: number }> = {
  low: { vol: 2.2, benchmarkVolMultiplier: 1.6 },
  value: { vol: 2.8, benchmarkVolMultiplier: 1.4 },
  momentum: { vol: 3.8, benchmarkVolMultiplier: 1.1 },
};
const DEFAULT_RISK = { vol: 2.5, benchmarkVolMultiplier: 1.3 };

// MOCK — 기간별 대략적인 방향성만 반영한 placeholder drift (실제 시장 수치 아님)
const PERIOD_BIAS: Record<string, { strategyDrift: number; benchmarkDrift: number }> = {
  'corona-crash': { strategyDrift: -0.35, benchmarkDrift: -0.65 },
  'downturn-2022': { strategyDrift: -0.12, benchmarkDrift: -0.28 },
  'recent-5y': { strategyDrift: 0.18, benchmarkDrift: 0.1 },
};
const DEFAULT_BIAS = { strategyDrift: 0.05, benchmarkDrift: 0.02 };

function lcgWalk(seed: number, n: number, vol: number, driftPerStep: number): number[] {
  let x = seed % 233280;
  let acc = 0;
  const out: number[] = [0];
  for (let i = 1; i < n; i++) {
    x = (x * 9301 + 49297) % 233280;
    const noise = (x / 233280 - 0.5) * vol * 2;
    acc += noise + driftPerStep;
    out.push(Math.round(acc * 100) / 100);
  }
  return out;
}

function dateLabels(startDate: string, endDate: string, n: number): string[] {
  const start = new Date(startDate).getTime();
  const end = new Date(endDate).getTime();
  const step = (end - start) / Math.max(1, n - 1);
  return Array.from({ length: n }, (_, i) => new Date(start + step * i).toISOString().slice(0, 10));
}

function maxDrawdown(series: number[]): number {
  let peak = series[0];
  let mdd = 0;
  for (const v of series) {
    peak = Math.max(peak, v);
    mdd = Math.min(mdd, v - peak);
  }
  return Math.round(mdd * 10) / 10;
}

function annualizedVolatility(series: number[], years: number): number {
  const steps = series.slice(1).map((v, i) => v - series[i]);
  if (steps.length === 0 || years <= 0) return 0;
  const mean = steps.reduce((a, b) => a + b, 0) / steps.length;
  const variance = steps.reduce((a, b) => a + (b - mean) ** 2, 0) / steps.length;
  const stdev = Math.sqrt(variance);
  const periodsPerYear = steps.length / years;
  return Math.round(stdev * Math.sqrt(periodsPerYear) * 10) / 10;
}

function cagrFrom(cumulativeReturn: number, years: number): number {
  const y = Math.max(years, 0.1);
  const cagr = ((1 + cumulativeReturn / 100) ** (1 / y) - 1) * 100;
  return Math.round(cagr * 10) / 10;
}

function computeMetrics(series: number[], years: number): BacktestMetrics {
  const cumulativeReturn = Math.round(series[series.length - 1] * 10) / 10;
  const cagr = cagrFrom(cumulativeReturn, years);
  const mdd = maxDrawdown(series);
  const volatility = annualizedVolatility(series, years);
  const sharpe = volatility >= 0.5 ? Math.round((cagr / volatility) * 100) / 100 : null;
  return { cumulativeReturn, cagr, mdd, volatility, sharpe };
}

function buildMockResult(strategyId: string, strategyName: string, period: BacktestPeriod): BacktestResult {
  const days = Math.max(
    1,
    (new Date(period.endDate).getTime() - new Date(period.startDate).getTime()) / 86_400_000,
  );
  const years = days / 365.25;
  const n = Math.min(120, Math.max(16, Math.round(days / 7)));

  const risk = STRATEGY_RISK[strategyId] ?? DEFAULT_RISK;
  const bias = PERIOD_BIAS[period.id] ?? DEFAULT_BIAS;
  const seed = strategyId.length * 7919 + period.id.length * 104_729;

  const strategySeries = lcgWalk(seed, n, risk.vol, bias.strategyDrift);
  const benchmarkSeries = lcgWalk(seed + 1, n, risk.vol * risk.benchmarkVolMultiplier, bias.benchmarkDrift);

  const labels = dateLabels(period.startDate, period.endDate, n);
  const series: BacktestSeriesPoint[] = labels.map((t, i) => ({
    t,
    strategy: strategySeries[i],
    benchmark: benchmarkSeries[i],
  }));

  const metrics = computeMetrics(strategySeries, years);
  const benchmarkMetricsFull = computeMetrics(benchmarkSeries, years);

  return {
    strategyId,
    strategyName,
    period,
    series,
    metrics,
    benchmarkName: 'KOSPI',
    benchmarkMetrics: { cumulativeReturn: benchmarkMetricsFull.cumulativeReturn, mdd: benchmarkMetricsFull.mdd },
  };
}

export function runBacktest(strategyId: string, strategyName: string, period: BacktestPeriod): Promise<BacktestResult> {
  return USE_MOCK
    ? delay(buildMockResult(strategyId, strategyName, period))
    : request<BacktestResult>('/run', { strategyId, periodId: period.id, startDate: period.startDate, endDate: period.endDate });
}

/* ----- MOCK AI 설명 -----
 * ctx 로 전달된 숫자만 참조해서 문장을 조립한다. 예측·추천성 표현이 들어갈
 * 자리를 애초에 만들지 않아서, 과거 데이터 한정 표현만 나오도록 강제한다.
 */
const PERIOD_OPENING: Record<string, string> = {
  'corona-crash': '코로나 폭락처럼 시장이 급격하게 떨어졌던 시기에는',
  'downturn-2022': '2022년처럼 시장 약세가 길게 이어졌던 기간에는',
  'recent-5y': '최근 5년처럼 상승과 하락을 모두 포함한 기간에는',
};

function buildMockExplanation(ctx: BacktestAiContext): string {
  const opening = PERIOD_OPENING[ctx.periodId] ?? '선택한 기간에는';
  const diff = Math.round((ctx.cumulativeReturn - ctx.benchmarkReturn) * 10) / 10;
  const compare =
    diff > 0
      ? `같은 기간 ${ctx.benchmarkName}(${ctx.benchmarkReturn}%)과 비교하면 하락폭이 ${Math.abs(diff)}%p 작았어요.`
      : diff < 0
        ? `같은 기간 ${ctx.benchmarkName}(${ctx.benchmarkReturn}%)과 비교하면 ${Math.abs(diff)}%p 낮은 성과였어요.`
        : `같은 기간 ${ctx.benchmarkName}과 비슷한 수준(${ctx.benchmarkReturn}%)이었어요.`;
  const sharpeSentence = ctx.sharpe != null ? ` 샤프 지수는 ${ctx.sharpe}였어요.` : '';

  return [
    `${opening} ${ctx.strategyName}은 과거 해당 구간에서 누적 ${ctx.cumulativeReturn}%를 기록했어요.`,
    compare,
    `이 기간 최대 낙폭은 ${ctx.mdd}%, 변동성은 ${ctx.volatility}%였어요.${sharpeSentence}`,
    '백테스트는 과거 데이터를 기반으로 한 결과이며, 미래 수익을 보장하지 않아요.',
  ].join(' ');
}

export function fetchAiExplanation(ctx: BacktestAiContext): Promise<BacktestAiExplanation> {
  return USE_MOCK
    ? delay({ explanation: buildMockExplanation(ctx), generatedAt: new Date().toISOString() })
    : request<BacktestAiExplanation>('/explain', ctx);
}
