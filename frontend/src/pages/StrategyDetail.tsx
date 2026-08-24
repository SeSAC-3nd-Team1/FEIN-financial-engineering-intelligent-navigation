import { useEffect, useMemo, useState } from 'react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { TooltipProps } from 'recharts';
import Header from '../components/Header';
import TermTooltip from '../components/TermTooltip';
import { fetchAiExplanation, runBacktest } from '../data/backtestApi';
import { AVAILABLE_DATA_RANGE, getRecommendedPeriods, validateCustomPeriod } from '../data/backtestPeriods';
import { STRATEGIES } from '../data/strategies';
import { won } from '../lib/validation';
import type { BacktestAiContext, BacktestPeriod, BacktestResult, Screen } from '../types';

interface Props {
  strategyId: string;
  userName: string;
  onNavigate: (s: Screen) => void;
  onStart: () => void;
  /** 이 전략으로 계좌 연결까지는 끝냈지만 "나중에 입금할게요"로 미룬 투자가 있으면 전달된다 */
  pendingDeposit?: { amount: number } | null;
  /** 위 배너의 CTA — 약관/계좌 단계를 다시 거치지 않고 곧장 입금 화면으로 이동한다 */
  onResumeDeposit?: () => void;
}

const PRINCIPAL = 10_000_000;

const METRIC_TERMS: Record<string, string> = {
  cumulativeReturn: '투자 시작 시점부터 해당 기간 끝까지 누적된 수익률이에요.',
  cagr: '연평균 성장률이에요. 기간 동안의 수익을 매년 일정하게 늘어난 것으로 환산한 값이에요.',
  mdd: '투자 기간 중 고점에서 가장 크게 떨어졌던 폭이에요.',
  volatility: '수익률이 오르내리는 정도예요. 클수록 등락이 심했다는 뜻이에요.',
  sharpe: '위험 대비 수익이 얼마나 좋았는지 보여주는 지표예요. 높을수록 위험 대비 수익이 좋았다는 뜻이에요.',
};

const fmtDate = (iso: string) => iso.replaceAll('-', '.');
const fmtAxisDate = (iso: string) => `${iso.slice(0, 4)}.${iso.slice(5, 7)}`;
const fmtTooltipDate = (iso: string) => `${iso.slice(0, 4)}년 ${Number(iso.slice(5, 7))}월`;
const fmtWon = (v: number) => `${Math.round(v / 10_000).toLocaleString('ko-KR')}만원`;
const signed = (v: number) => `${v > 0 ? '+' : ''}${v}%`;

/** 03 전략 상세 — 추천 기간(또는 직접 설정한 기간)으로 전략을 직접 체험한 뒤 바로 투자 시작으로 이어진다 */
export default function StrategyDetail({ strategyId, userName, onNavigate, onStart, pendingDeposit, onResumeDeposit }: Props) {
  const strategy = STRATEGIES.find((s) => s.id === strategyId) ?? STRATEGIES[0];
  const periods = useMemo(() => getRecommendedPeriods(), []);

  const [periodMode, setPeriodMode] = useState<'preset' | 'custom'>('preset');
  const [presetPeriodId, setPresetPeriodId] = useState(periods[0].id);
  const [customPeriod, setCustomPeriod] = useState<{ startDate: string; endDate: string } | null>(null);

  const [customPanelOpen, setCustomPanelOpen] = useState(false);
  const [draftStart, setDraftStart] = useState('');
  const [draftEnd, setDraftEnd] = useState('');
  const [customError, setCustomError] = useState<string | null>(null);

  const [retryToken, setRetryToken] = useState(0);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [resultLoading, setResultLoading] = useState(false);
  const [resultError, setResultError] = useState<string | null>(null);

  const [aiHeadline, setAiHeadline] = useState<string | null>(null);
  const [aiOverview, setAiOverview] = useState<string | null>(null);
  const [aiCaution, setAiCaution] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  // 추천 기간 또는 직접 설정 중 지금 적용된 기간 하나 — 두 모드가 항상 이 값 하나로 합쳐진다
  const activePeriod: BacktestPeriod = useMemo(() => {
    if (periodMode === 'custom' && customPeriod) {
      return { id: 'custom', label: '직접 설정', startDate: customPeriod.startDate, endDate: customPeriod.endDate, description: '' };
    }
    return periods.find((p) => p.id === presetPeriodId) ?? periods[0];
  }, [periodMode, customPeriod, presetPeriodId, periods]);

  // 전략이 바뀌면(다른 strategyId로 재진입) 기간 선택은 추천 기간 기본값으로 되돌린다
  useEffect(() => {
    setPeriodMode('preset');
    setPresetPeriodId(periods[0].id);
    setCustomPeriod(null);
    setCustomPanelOpen(false);
  }, [strategyId, periods]);

  const selectPreset = (id: string) => {
    setPeriodMode('preset');
    setPresetPeriodId(id);
    setCustomPanelOpen(false);
  };

  const applyCustomPeriod = () => {
    const err = validateCustomPeriod(draftStart, draftEnd);
    if (err) { setCustomError(err); return; }
    setCustomError(null);
    setCustomPeriod({ startDate: draftStart, endDate: draftEnd });
    setPeriodMode('custom');
  };

  // 기간이 바뀌면 이전 결과와 AI 설명을 함께 리셋하고 새로 받아온다 — 전략은 그대로 둔다.
  useEffect(() => {
    let cancelled = false;
    setResultLoading(true);
    setResultError(null);
    setResult(null);
    setAiHeadline(null);
    setAiOverview(null);
    setAiCaution(null);
    setAiError(null);
    setAiLoading(false);

    runBacktest(strategy.id, strategy.name, activePeriod)
      .then((r) => { if (!cancelled) setResult(r); })
      .catch((e) => { if (!cancelled) setResultError(e instanceof Error ? e.message : '백테스트 결과를 불러오지 못했어요.'); })
      .finally(() => { if (!cancelled) setResultLoading(false); });

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategy.id, activePeriod, retryToken]);

  // AI 설명은 백테스트 결과가 성공적으로 온 뒤에만, 그 결과 값 그대로를 근거로 요청한다.
  // 백테스트 계산과는 완전히 분리된 상태라 AI 호출이 실패해도 위 결과·차트·지표는 그대로 남는다.
  useEffect(() => {
    if (!result) return;
    let cancelled = false;
    setAiLoading(true);
    setAiError(null);

    const ctx: BacktestAiContext = {
      strategyName: result.strategyName,
      periodType: result.period.id === 'custom' ? 'custom' : 'preset',
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
      .then((r) => { if (!cancelled) { setAiHeadline(r.headline); setAiOverview(r.overview); setAiCaution(r.caution); } })
      .catch(() => { if (!cancelled) setAiError('물방개가 설명을 준비하지 못했어요. 백테스트 결과는 위 지표에서 확인할 수 있어요.'); })
      .finally(() => { if (!cancelled) setAiLoading(false); });

    return () => { cancelled = true; };
  }, [result]);

  const chartData = result?.series.map((p) => ({ t: p.t, [result.strategyName]: p.strategy, [result.benchmarkName]: p.benchmark })) ?? [];
  const finalAmount = result ? Math.round(PRINCIPAL * (1 + result.metrics.cumulativeReturn / 100)) : 0;
  const diffAmount = finalAmount - PRINCIPAL;
  const tickInterval = Math.max(0, Math.ceil((chartData.length || 1) / 6) - 1);

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-[#3F5222]">✦ 나와 {strategy.match}% 잘 맞는 전략</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">{strategy.name}</h1>
            <p className="max-w-[820px] text-[19px] leading-8 text-muted">{strategy.why}</p>
          </section>

          {pendingDeposit && (
            <section className="flex items-center justify-between gap-6 rounded-card bg-[#F8FCEE] px-9 py-7 shadow-[0_0_0_1px_#C6F04D_inset]">
              <div className="flex flex-col gap-1.5">
                <span className="text-[15px] font-semibold text-[#3F5222]">입금이 필요해요</span>
                <p className="text-lg font-bold text-ink">
                  {won(pendingDeposit.amount)} 입금하면 {strategy.name}으로 투자를 시작할 수 있어요.
                </p>
              </div>
              <button
                onClick={onResumeDeposit}
                className="shrink-0 rounded-field bg-lime px-7 py-4 text-base font-bold text-navy"
              >
                입금하러 가기 →
              </button>
            </section>
          )}

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex flex-col gap-2.5">
              <h2 className="text-[26px] font-bold tracking-[-0.025em]">언제를 골라볼까요?</h2>
              <p className="text-[17px] text-muted">1,000만원을 넣었다고 가정하고, 구간을 바꿔가며 결과를 볼 수 있어요.</p>
            </div>

            <div className="flex flex-wrap gap-3">
              {periods.map((p) => (
                <button
                  key={p.id}
                  onClick={() => selectPreset(p.id)}
                  className={`rounded-full px-6 py-3.5 text-[17px] font-semibold ${
                    periodMode === 'preset' && p.id === presetPeriodId ? 'bg-lime text-navy' : 'bg-[#F4F6F1] text-muted'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>

            <p className="text-[15px] leading-6 text-muted">
              {activePeriod.label} · {fmtDate(activePeriod.startDate)} — {fmtDate(activePeriod.endDate)}
              {periodMode === 'preset' && activePeriod.description && <><br />{activePeriod.description}</>}
            </p>

            <button
              onClick={() => setCustomPanelOpen((o) => !o)}
              className="self-start text-[15px] font-semibold text-navy underline"
            >
              원하는 기간이 있나요? 직접 설정 →
            </button>

            {customPanelOpen && (
              <div className="flex flex-col gap-3.5 rounded-[16px] bg-[#F8F9F6] p-7">
                <span className="text-[15px] font-bold">직접 기간 설정</span>
                <div className="flex items-center gap-3">
                  <input
                    type="date"
                    value={draftStart}
                    min={AVAILABLE_DATA_RANGE.minDate}
                    max={AVAILABLE_DATA_RANGE.maxDate}
                    onChange={(e) => setDraftStart(e.target.value)}
                    className="rounded-field bg-surface px-4 py-3 text-[15px] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
                  />
                  <span className="text-muted">→</span>
                  <input
                    type="date"
                    value={draftEnd}
                    min={AVAILABLE_DATA_RANGE.minDate}
                    max={AVAILABLE_DATA_RANGE.maxDate}
                    onChange={(e) => setDraftEnd(e.target.value)}
                    className="rounded-field bg-surface px-4 py-3 text-[15px] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
                  />
                </div>
                {customError && <span className="text-sm text-up">{customError}</span>}
                <button onClick={applyCustomPeriod} className="self-start rounded-field bg-lime px-7 py-3.5 text-[15px] font-bold text-navy">
                  이 기간으로 확인하기
                </button>
              </div>
            )}
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
                    {result.period.label} · {fmtDate(result.period.startDate)} — {fmtDate(result.period.endDate)} · 투자금 1,000만원
                  </span>
                </div>

                <div className="flex items-baseline gap-3.5">
                  <span className="text-[44px] font-bold tracking-[-0.035em]">{fmtWon(finalAmount)}</span>
                  <span className={`text-[19px] font-semibold ${diffAmount >= 0 ? 'text-up' : 'text-down'}`}>
                    {diffAmount >= 0 ? '+' : ''}{fmtWon(diffAmount)} ({signed(result.metrics.cumulativeReturn)})
                  </span>
                </div>

                <div className="h-[300px] w-full">
                  <ResponsiveContainer>
                    <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke="#F0F2ED" vertical={false} />
                      <XAxis
                        dataKey="t"
                        tick={{ fill: '#8A948C', fontSize: 12 }}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={fmtAxisDate}
                        interval={tickInterval}
                      />
                      <YAxis
                        tick={{ fill: '#8A948C', fontSize: 13 }}
                        axisLine={false}
                        tickLine={false}
                        width={56}
                        tickFormatter={(v: number) => `${v}%`}
                      />
                      <Tooltip content={<BacktestChartTooltip strategyName={result.strategyName} />} />
                      <Legend iconType="plainline" wrapperStyle={{ fontSize: 15, color: '#5C665F' }} />
                      <Line type="monotone" dataKey={result.benchmarkName} stroke="#C3CBC4" strokeWidth={3.5} dot={false} />
                      <Line type="monotone" dataKey={result.strategyName} stroke="#18243A" strokeWidth={5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {aiHeadline && (
                  <div className="flex items-center gap-4 rounded-[16px] bg-[#F8FCEE] px-8 py-6">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-lime text-base text-navy">✦</span>
                    <span className="text-[19px] font-bold leading-[28px] tracking-[-0.02em]">{aiHeadline}</span>
                  </div>
                )}

                <div className="grid grid-cols-4 gap-8 border-t border-[#F0F2ED] pt-7">
                  <MetricTile label="누적 수익률" value={signed(result.metrics.cumulativeReturn)} termKey="cumulativeReturn" />
                  <MetricTile label="CAGR" value={signed(result.metrics.cagr)} termKey="cagr" />
                  <MetricTile label="MDD" value={`${result.metrics.mdd}%`} accent termKey="mdd" />
                  <MetricTile label="변동성" value={`${result.metrics.volatility}%`} termKey="volatility" />
                  {result.metrics.sharpe != null && (
                    <MetricTile label="샤프 지수" value={`${result.metrics.sharpe}`} termKey="sharpe" />
                  )}
                  <MetricTile label="리밸런싱" value={strategy.rebalance} />
                </div>
              </section>

              <section className="flex gap-6 rounded-[20px] bg-[#F8FCEE] px-10 py-9">
                <img
                  src={aiLoading ? '/character-thinking.png' : '/character-analyze.png'}
                  alt="물방개"
                  className="h-20 w-20 shrink-0 object-contain"
                />
                <div className="flex flex-1 flex-col gap-4">
                  <span className="text-[22px] font-bold leading-[34px] tracking-[-0.025em]">
                    {aiLoading ? '물방개가 결과를 살펴보고 있어요...' : '물방개가 결과를 쉽게 설명해드릴게요'}
                  </span>
                  {aiError && <p className="text-lg leading-[30px] text-[#3F4A43]">{aiError}</p>}
                  {aiOverview && (
                    <div className="flex flex-col gap-1.5">
                      <span className="text-[15px] font-bold text-[#3F5222]">한눈에 보면</span>
                      <p className="max-w-[760px] text-lg leading-[30px] text-[#3F4A43]">{aiOverview}</p>
                    </div>
                  )}
                  {aiCaution && (
                    <div className="flex flex-col gap-1.5">
                      <span className="text-[15px] font-bold text-[#3F5222]">주의해서 볼 점</span>
                      <p className="max-w-[760px] text-lg leading-[30px] text-[#3F4A43]">{aiCaution}</p>
                    </div>
                  )}
                </div>
              </section>
            </>
          )}

          <section className="flex items-center justify-between gap-8 rounded-card bg-navy px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-2xl font-bold tracking-[-0.025em] text-white">이 전략으로 시작해볼까요?</span>
              <span className="text-[17px] leading-7 text-[#B9C2BA]">10만원부터 시작할 수 있고, 전략은 언제든 바꿀 수 있어요.</span>
            </div>
            <button onClick={onStart} className="shrink-0 rounded-field bg-lime px-9 py-5 text-lg font-bold text-navy">
              이 전략으로 시작하기 →
            </button>
          </section>

          <p className="text-sm leading-[22px] text-subtle">
            ※ 백테스트 결과는 과거 데이터 기반 예시이며 미래 수익을 보장하지 않습니다.
          </p>
        </div>
      </main>
    </div>
  );
}

function MetricTile({ label, value, accent, termKey }: { label: string; value: string; accent?: boolean; termKey?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-1">
        <span className="text-[15px] text-muted">{label}</span>
        {termKey && <TermTooltip label={label} description={METRIC_TERMS[termKey]} />}
      </div>
      <span className={`text-[22px] font-bold ${accent ? 'text-down' : ''}`}>{value}</span>
    </div>
  );
}

/** 차트 hover tooltip — 첫 줄에 실제 데이터 포인트의 날짜(YYYY년 M월), 그 아래 전략/벤치마크 수익률 */
function BacktestChartTooltip({ active, payload, label, strategyName }: TooltipProps<number, string> & { strategyName: string }) {
  if (!active || !payload || payload.length === 0) return null;
  const sorted = [...payload].sort((a) => (a.dataKey === strategyName ? -1 : 1));
  return (
    <div className="rounded-[10px] bg-white px-4 py-3 text-[14px] shadow-[0_8px_24px_rgba(24,36,58,0.18)]">
      <div className="mb-1.5 font-semibold text-ink">{fmtTooltipDate(String(label ?? ''))}</div>
      <div className="flex flex-col gap-1">
        {sorted.map((p) => (
          <div key={String(p.dataKey)} className="flex items-center gap-2.5">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: p.dataKey === strategyName ? '#18243A' : '#C3CBC4' }} />
            <span className="w-16 shrink-0 text-muted">{p.dataKey}</span>
            <span className="font-semibold text-ink">{signed(Number(p.value))}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
