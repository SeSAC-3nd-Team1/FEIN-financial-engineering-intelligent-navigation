import { STRATEGIES } from './strategies';
import type { BacktestPeriod, BacktestResult, BacktestSeriesPoint } from '../types';
import type { BacktestAvailableRange } from './backtestApi';

/**
 * Frontend 전용 Mock Backtest 데이터 — 실제 백테스트 모델/KRX 데이터 연동 전까지 Strategy Detail의
 * UX를 화면에서 확인하기 위한 예시 데이터다. backtestApi.ts의 USE_MOCK_BACKTEST가 켜졌을 때만
 * 쓰이고, 실제 API 응답과 동일한 BacktestResult/BacktestAvailableRange 타입을 그대로 따른다 —
 * 그래서 이 파일을 걷어내고 실제 API 호출로만 바꿔도 StrategyDetail.tsx는 손댈 필요가 없다.
 *
 * 현재는 대표 preset("코로나 폭락") 1개만 지원한다 — 그 외 기간/직접 설정은 비회원이면 어차피
 * 기존 로그인 lock에 걸리고, 로그인 사용자가 눌러도 "준비 중" 에러로 기존 Error UI를 그대로 재사용한다.
 */

const CORONA_CRASH_PERIOD_ID = 'corona-crash';

/** getRecommendedPeriods()가 실제와 동일하게 코로나 폭락/2022 하락장/최근 5년을 모두 보여주도록,
 * 그 기간들을 모두 포함하는 넉넉한 범위를 준다. */
export const MOCK_AVAILABLE_RANGE: BacktestAvailableRange = {
  minDate: '2018-01-01',
  maxDate: new Date().toISOString().slice(0, 10),
};

const round1 = (v: number) => Math.round(v * 10) / 10;
const pct = (s: string) => parseFloat(s);

function metricsOf(strategyId: string) {
  const s = STRATEGIES.find((x) => x.id === strategyId) ?? STRATEGIES[0];
  return { mdd: pct(s.mdd), vol: pct(s.vol), sharpe: pct(s.sharpe) };
}

interface CrashScenario {
  /** 기간 종료 시점의 누적 수익률(%) */
  finalReturn: number;
  /** 기간 중 최저점(=MDD, %) */
  troughReturn: number;
}

/**
 * 2020 코로나 폭락 기간 시나리오 — 임의로 새 수치를 지어내지 않고 기존 placeholder를 재사용한다.
 * low: 이전 비로그인 Home 마케팅 카드에 있던 "830만원 / -17.0% / KOSPI -32%" 수치.
 * value/momentum: 해당 필드가 따로 없어 STRATEGIES의 기존 mdd를 저점이자 종료 시점 값으로 그대로 쓴다
 * (급락 후 반등 없이 저점에서 마감하는 모양 — 낙관적으로 새 숫자를 보태지 않기 위함).
 */
const CRASH_SCENARIOS: Record<string, CrashScenario> = {
  low: { finalReturn: -17, troughReturn: metricsOf('low').mdd },
  value: { finalReturn: metricsOf('value').mdd, troughReturn: metricsOf('value').mdd },
  momentum: { finalReturn: metricsOf('momentum').mdd, troughReturn: metricsOf('momentum').mdd },
};

/** 같은 기간의 벤치마크(KOSPI)는 전략과 무관하게 동일해야 한다 — 실제 API와 같은 성격 */
const BENCHMARK_FINAL = -32;
const BENCHMARK_TROUGH = -34;

/** 0→저점→종료값의 3단 선형 보간으로 급락 후 (부분)회복하는 곡선을 만든다 */
function buildSeries(startDate: string, endDate: string, scenario: { trough: number; final: number }, benchmark: { trough: number; final: number }): BacktestSeriesPoint[] {
  const start = new Date(`${startDate}T00:00:00Z`).getTime();
  const end = new Date(`${endDate}T00:00:00Z`).getTime();
  const POINTS = 24;
  const TROUGH_AT = 0.4;
  const at = (t: number, trough: number, final: number) =>
    round1(t <= TROUGH_AT ? trough * (t / TROUGH_AT) : trough + (final - trough) * ((t - TROUGH_AT) / (1 - TROUGH_AT)));

  const series: BacktestSeriesPoint[] = [];
  for (let i = 0; i <= POINTS; i += 1) {
    const t = i / POINTS;
    series.push({
      t: new Date(start + (end - start) * t).toISOString().slice(0, 10),
      strategy: at(t, scenario.trough, scenario.final),
      benchmark: at(t, benchmark.trough, benchmark.final),
    });
  }
  return series;
}

function annualize(cumulativeReturnPct: number, startDate: string, endDate: string): number {
  const days = Math.max(1, (new Date(endDate).getTime() - new Date(startDate).getTime()) / 86_400_000);
  const years = days / 365.25;
  const growth = 1 + cumulativeReturnPct / 100;
  if (growth <= 0) return -100;
  return round1((growth ** (1 / years) - 1) * 100);
}

/** period.id가 'corona-crash'가 아니면 "준비 중" 에러로 reject — StrategyDetail의 기존 Error UI를 그대로 재사용한다 */
export function getMockBacktestResult(strategyId: string, strategyName: string, period: BacktestPeriod): Promise<BacktestResult> {
  if (period.id !== CORONA_CRASH_PERIOD_ID) {
    return Promise.reject(
      new Error('이 기간의 예시 데이터는 아직 준비 중이에요. "코로나 폭락" 기간에서 확인해보세요.'),
    );
  }

  const scenario = CRASH_SCENARIOS[strategyId] ?? CRASH_SCENARIOS.low;
  const { vol, sharpe } = metricsOf(strategyId);
  const series = buildSeries(
    period.startDate,
    period.endDate,
    { trough: scenario.troughReturn, final: scenario.finalReturn },
    { trough: BENCHMARK_TROUGH, final: BENCHMARK_FINAL },
  );

  return Promise.resolve({
    strategyId,
    strategyName,
    period,
    series,
    metrics: {
      cumulativeReturn: scenario.finalReturn,
      cagr: annualize(scenario.finalReturn, period.startDate, period.endDate),
      mdd: scenario.troughReturn,
      volatility: vol,
      sharpe,
    },
    benchmarkName: 'KOSPI',
    benchmarkMetrics: { cumulativeReturn: BENCHMARK_FINAL, mdd: BENCHMARK_TROUGH },
  });
}
