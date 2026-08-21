import { useEffect, useMemo, useState } from 'react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import Header from '../components/Header';
import TermTooltip from '../components/TermTooltip';
import { fetchAiExplanation, runBacktest } from '../data/backtestApi';
import { getRecommendedPeriods } from '../data/backtestPeriods';
import { STRATEGIES } from '../data/strategies';
import type { BacktestAiContext, BacktestPeriod, BacktestResult, Screen } from '../types';

interface Props {
  strategyId?: string;
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
}

const METRIC_TERMS: Record<string, string> = {
  cumulativeReturn: '투자 시작 시점부터 해당 기간 끝까지 누적된 수익률이에요.',
  cagr: '연평균 성장률이에요. 기간 동안의 수익을 매년 일정하게 늘어난 것으로 환산한 값이에요.',
  mdd: '투자 기간 중 고점에서 가장 크게 떨어졌던 폭이에요.',
  volatility: '수익률이 오르내리는 정도예요. 클수록 등락이 심했다는 뜻이에요.',
  sharpe: '위험 대비 수익이 얼마나 좋았는지 보여주는 지표예요. 높을수록 위험 대비 수익이 좋았다는 뜻이에요.',
};

const fmtDate = (iso: string) => iso.replaceAll('-', '.');
const signed = (v: number) => `${v > 0 ? '+' : ''}${v}%`;

/** 04 백테스트 — 추천 기간 기준으로 전략의 과거 성과·위험을 확인하고 AI 설명을 받는다 */
export default function Backtest({ strategyId: initialStrategyId, userName, onNavigate, onBack }: Props) {
  const periods = useMemo(() => getRecommendedPeriods(), []);
  const [strategyId, setStrategyId] = useState(initialStrategyId ?? STRATEGIES[0].id);
  const [selectedPeriod, setSelectedPeriod] = useState<BacktestPeriod>(periods[0]);
  const [retryToken, setRetryToken] = useState(0);

  const [result, setResult] = useState<BacktestResult | null>(null);
  const [resultLoading, setResultLoading] = useState(false);
  const [resultError, setResultError] = useState<string | null>(null);

  const [aiExplanation, setAiExplanation] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const strategy = STRATEGIES.find((s) => s.id === strategyId) ?? STRATEGIES[0];

  // 전략/기간이 바뀌면 이전 결과와 AI 설명을 함께 리셋하고 새로 받아온다 —
  // 새 지표에 헌 AI 설명이 잠깐이라도 같이 보이는 상황을 막는다.
  useEffect(() => {
    let cancelled = false;
    setResultLoading(true);
    setResultError(null);
    setResult(null);
    setAiExplanation(null);
    setAiError(null);
    setAiLoading(false);

    runBacktest(strategyId, strategy.name, selectedPeriod)
      .then((r) => { if (!cancelled) setResult(r); })
      .catch((e) => { if (!cancelled) setResultError(e instanceof Error ? e.message : '백테스트 결과를 불러오지 못했어요.'); })
      .finally(() => { if (!cancelled) setResultLoading(false); });

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategyId, selectedPeriod, retryToken]);

  // AI 설명은 백테스트 결과가 성공적으로 온 뒤에만, 그 결과 값 그대로를 근거로 요청한다.
  useEffect(() => {
    if (!result) return;
    let cancelled = false;
    setAiLoading(true);
    setAiError(null);

    const ctx: BacktestAiContext = {
      strategyName: result.strategyName,
      periodId: result.period.id,
      periodLabel: result.period.label,
      periodDescription: result.period.description,
      startDate: result.period.startDate,
      endDate: result.period.endDate,
      cumulativeReturn: result.metrics.cumulativeReturn,
      cagr: result.metrics.cagr,
      mdd: result.metrics.mdd,
      volatility: result.metrics.volatility,
      sharpe: result.metrics.sharpe,
      benchmarkName: result.benchmarkName,
      benchmarkReturn: result.benchmarkMetrics.cumulativeReturn,
      benchmarkMdd: result.benchmarkMetrics.mdd,
    };

    fetchAiExplanation(ctx)
      .then((r) => { if (!cancelled) setAiExplanation(r.explanation); })
      .catch(() => { if (!cancelled) setAiError('AI 설명을 불러오지 못했어요. 백테스트 결과는 위 지표에서 확인할 수 있어요.'); })
      .finally(() => { if (!cancelled) setAiLoading(false); });

    return () => { cancelled = true; };
  }, [result]);

  const chartData = result?.series.map((p) => ({ t: p.t, [result.strategyName]: p.strategy, [result.benchmarkName]: p.benchmark })) ?? [];

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <button onClick={onBack} className="self-start text-base font-semibold text-muted">← 전략으로 돌아가기</button>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">백테스트</h1>
            <p className="max-w-[820px] text-[19px] leading-8 text-muted">
              선택한 전략이 대표적인 과거 시장 상황에서 어떤 성과와 위험을 보였는지 확인해보세요.
            </p>
          </section>

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex flex-col gap-4">
              <h2 className="text-[22px] font-bold tracking-[-0.025em]">전략</h2>
              <div className="flex flex-wrap gap-3">
                {STRATEGIES.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setStrategyId(s.id)}
                    className={`rounded-full px-6 py-3.5 text-[17px] font-semibold ${
                      s.id === strategyId ? 'bg-lime text-navy' : 'bg-[#F4F6F1] text-muted'
                    }`}
                  >
                    {s.name}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-4 border-t border-[#F0F2ED] pt-7">
              <h2 className="text-[22px] font-bold tracking-[-0.025em]">추천 기간</h2>
              <div className="flex flex-wrap gap-3">
                {periods.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setSelectedPeriod(p)}
                    className={`rounded-full px-6 py-3.5 text-[17px] font-semibold ${
                      p.id === selectedPeriod.id ? 'bg-lime text-navy' : 'bg-[#F4F6F1] text-muted'
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
                {/* P2: 직접 설정 진입점 — CustomDateRangePicker 준비되면 여기 추가 */}
              </div>
              <p className="text-[15px] leading-6 text-muted">
                {selectedPeriod.label} · {fmtDate(selectedPeriod.startDate)} — {fmtDate(selectedPeriod.endDate)}
                <br />
                {selectedPeriod.description}
              </p>
            </div>
          </section>

          {resultLoading && (
            <section className="flex animate-pulse flex-col gap-4 rounded-card bg-surface p-12">
              <div className="h-8 w-1/3 rounded-md bg-[#F0F2ED]" />
              <div className="h-[300px] w-full rounded-[14px] bg-[#F4F6F1]" />
              <div className="grid grid-cols-4 gap-8">
                {[0, 1, 2, 3].map((i) => <div key={i} className="h-14 rounded-md bg-[#F0F2ED]" />)}
              </div>
            </section>
          )}

          {resultError && (
            <section className="flex flex-col items-center gap-5 rounded-card bg-surface px-10 py-20">
              <div className="flex h-14 w-14 items-center justify-center rounded-[18px] bg-[#FDECEC] text-2xl font-bold text-[#D64545]">!</div>
              <h2 className="text-2xl font-bold tracking-[-0.025em]">백테스트 결과를 불러올 수 없어요</h2>
              <p className="max-w-[520px] text-center text-[17px] leading-7 text-muted">{resultError}</p>
              <button onClick={() => setRetryToken((t) => t + 1)} className="rounded-field bg-lime px-8 py-4 text-[17px] font-bold text-navy">
                다시 시도하기
              </button>
            </section>
          )}

          {result && (
            <>
              <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
                <div className="flex flex-col gap-2">
                  <span className="text-base text-muted">
                    {result.period.label} · {fmtDate(result.period.startDate)} — {fmtDate(result.period.endDate)}
                  </span>
                  <span className="text-[22px] font-bold tracking-[-0.025em]">{result.strategyName}</span>
                </div>

                <div className="flex gap-14">
                  <div className="flex flex-col gap-1.5">
                    <span className="text-[15px] text-muted">누적 수익률</span>
                    <span className={`text-[40px] font-bold tracking-[-0.035em] ${result.metrics.cumulativeReturn >= 0 ? 'text-up' : 'text-down'}`}>
                      {signed(result.metrics.cumulativeReturn)}
                    </span>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <span className="text-[15px] text-muted">최대 낙폭</span>
                    <span className="text-[40px] font-bold tracking-[-0.035em] text-down">{result.metrics.mdd}%</span>
                  </div>
                </div>

                <div className="h-[300px] w-full">
                  <ResponsiveContainer>
                    <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke="#F0F2ED" vertical={false} />
                      <XAxis dataKey="t" hide />
                      <YAxis
                        tick={{ fill: '#8A948C', fontSize: 13 }}
                        axisLine={false}
                        tickLine={false}
                        width={56}
                        tickFormatter={(v: number) => `${v}%`}
                      />
                      <Tooltip formatter={(v: number) => `${v}%`} labelFormatter={(l) => l} />
                      <Legend iconType="plainline" wrapperStyle={{ fontSize: 15, color: '#5C665F' }} />
                      <Line type="monotone" dataKey={result.benchmarkName} stroke="#C3CBC4" strokeWidth={3.5} dot={false} />
                      <Line type="monotone" dataKey={result.strategyName} stroke="#18243A" strokeWidth={5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                <div className="grid grid-cols-4 gap-8 border-t border-[#F0F2ED] pt-7">
                  <MetricTile label="누적 수익률" value={signed(result.metrics.cumulativeReturn)} termKey="cumulativeReturn" />
                  <MetricTile label="CAGR" value={signed(result.metrics.cagr)} termKey="cagr" />
                  <MetricTile label="MDD" value={`${result.metrics.mdd}%`} accent termKey="mdd" />
                  <MetricTile label="변동성" value={`${result.metrics.volatility}%`} termKey="volatility" />
                  {result.metrics.sharpe != null && (
                    <MetricTile label="샤프 지수" value={`${result.metrics.sharpe}`} termKey="sharpe" />
                  )}
                </div>
              </section>

              <section className="flex gap-5 rounded-[20px] bg-[#F8FCEE] px-10 py-9">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-lime text-lg text-navy">✦</div>
                <div className="flex flex-1 flex-col gap-3">
                  <span className="text-[22px] font-bold leading-[34px] tracking-[-0.025em]">AI가 백테스트 결과를 쉽게 설명해드릴게요</span>
                  {aiLoading && <p className="text-lg leading-[30px] text-[#3F4A43]">백테스트 결과를 분석하고 있어요...</p>}
                  {aiError && <p className="text-lg leading-[30px] text-[#3F4A43]">{aiError}</p>}
                  {aiExplanation && <p className="max-w-[760px] text-lg leading-[30px] text-[#3F4A43]">{aiExplanation}</p>}
                </div>
              </section>
            </>
          )}

          <p className="text-sm leading-[22px] text-subtle">
            ※ 백테스트 결과는 과거 데이터 기반 예시이며 미래 수익을 보장하지 않습니다.
          </p>
        </div>
      </main>
    </div>
  );
}

function MetricTile({ label, value, accent, termKey }: { label: string; value: string; accent?: boolean; termKey: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-1">
        <span className="text-[15px] text-muted">{label}</span>
        <TermTooltip label={label} description={METRIC_TERMS[termKey]} />
      </div>
      <span className={`text-[22px] font-bold ${accent ? 'text-down' : ''}`}>{value}</span>
    </div>
  );
}
