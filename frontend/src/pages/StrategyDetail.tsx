import { useEffect, useMemo, useState } from 'react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { TooltipProps } from 'recharts';
import Header from '../components/Header';
import TermTooltip from '../components/TermTooltip';
import { fetchAiExplanation, getBacktestAvailableRange, runBacktest, USE_MOCK_BACKTEST } from '../data/backtestApi';
import type { BacktestAvailableRange } from '../data/backtestApi';
import { getRecommendedPeriods, validateCustomPeriod } from '../data/backtestPeriods';
import type { StrategyRecommendationItemResponse, StrategyResponse } from '../lib/backendApi';
import { won } from '../lib/validation';
import { useTradingData } from '../hooks/useTradingData';
import { useAuthStore } from '../store/authStore';
import { useInvestmentStore } from '../store/investmentStore';
import { useTradingStore } from '../store/tradingStore';
import type { BacktestAiContext, BacktestPeriod, BacktestResult, Screen } from '../types';

interface Props {
  strategy: StrategyResponse;
  strategyCatalog: StrategyResponse[];
  recommendation?: StrategyRecommendationItemResponse | null;
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
  onStart: () => void;
  /** 백테스트의 잠긴 기간/직접 설정(Inline Login CTA)에서 로그인 화면으로 보낼 때 사용 —
   * 로그인 후 Portfolio가 아니라 이 화면으로 복귀시키기 위해 App.tsx가 별도로 처리한다 */
  onRequestLoginForBacktest: () => void;
  /** "이 전략으로 변경하기" 확인 — 실제 계좌 전략 변경 API(ensureAccount/selectStrategyApi)를 거친 뒤
   * App.tsx가 로컬 activeStrategyId 갱신과 Portfolio 이동까지 처리한다. 실패하면 reject된다. */
  onConfirmStrategyChange: () => Promise<void>;
  /** 이 전략으로 계좌 연결까지는 끝냈지만 "나중에 입금할게요"로 미룬 투자가 있으면 전달된다 */
  pendingDeposit?: { amount: number } | null;
  /** 위 배너의 CTA — 약관/계좌 단계를 다시 거치지 않고 곧장 입금 화면으로 이동한다 */
  onResumeDeposit?: () => void;
}

const PRINCIPAL = 10_000_000;

const REBALANCE_LABEL: Record<string, string> = {
  WEEKLY: '주 1회', MONTHLY: '월 1회', QUARTERLY: '분기 1회', YEARLY: '연 1회',
};

const METRIC_TERMS: Record<string, string> = {
  cumulativeReturn: '투자 시작 시점부터 해당 기간 끝까지 누적된 수익률이에요.',
  cagr: '투자 기간의 전체 성과를 1년 평균 수익률로 환산한 값이에요.',
  mdd: '투자 기간 중 가장 크게 떨어졌던 폭이에요. 숫자가 작을수록 하락 위험이 상대적으로 낮아요.',
  volatility: '수익률이 얼마나 크게 오르내렸는지를 보여줘요. 낮을수록 움직임이 비교적 안정적이에요.',
  sharpe: '감수한 위험에 비해 얼마나 효율적으로 수익을 냈는지 보여줘요. 일반적으로 높을수록 좋아요.',
};

const METRIC_LABELS: Record<string, string> = {
  cagr: '연평균 수익률(CAGR)',
  mdd: '최대 낙폭(MDD)',
};

const fmtDate = (iso: string) => iso.replaceAll('-', '.');
const fmtAxisDate = (iso: string) => `${iso.slice(0, 4)}.${iso.slice(5, 7)}`;
const fmtTooltipDate = (iso: string) => `${iso.slice(0, 4)}년 ${Number(iso.slice(5, 7))}월`;
const fmtWon = (v: number) => `${Math.round(v / 10_000).toLocaleString('ko-KR')}만원`;
const signed = (v: number) => `${v > 0 ? '+' : ''}${v}%`;

/** 03 전략 상세 — 추천 기간(또는 직접 설정한 기간)으로 전략을 직접 체험한 뒤 바로 투자 시작으로 이어진다 */
export default function StrategyDetail({
  strategy, strategyCatalog, recommendation, userName, onNavigate, onStart, onRequestLoginForBacktest,
  onBack, onConfirmStrategyChange, pendingDeposit, onResumeDeposit,
}: Props) {
  const strategyId = strategy.id;
  // 비회원 공개 정책: 전략을 읽고 백테스트 기본 결과를 보는 것은 PUBLIC이지만, "나와 몇% 잘
  // 맞는지" 같은 개인화 적합도는 로그인 + 투자성향 진단 완료 사용자에게만 보여준다.
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);
  const investorProfileCompleted = useAuthStore((s) => s.investorProfileCompleted);
  const showSuitability = isLoggedIn && investorProfileCompleted;

  // "계좌 1개 = 운용방식 1개 = 활성 전략 1개" 정책 — 지금 활성 투자(activeMode)가 있으면 그 계좌의
  // activeStrategyId와 이 화면의 strategyId를 비교해 CTA를 셋 중 하나로 분기한다. 비회원/미투자
  // 사용자는 accountsByMode·activeMode가 항상 비어있어 자연히 'start'가 된다.
  const accountsByMode = useInvestmentStore((s) => s.accountsByMode);
  const activeMode = useInvestmentStore((s) => s.activeMode);
  const activeAccount = activeMode ? accountsByMode[activeMode] : null;
  // 위 로컬 기록은 이 브라우저에서 투자 시작/전략 변경을 실제로 거친 세션에만 채워진다. 새
  // 브라우저나 localStorage가 초기화된 환경에서는 실제 계좌(백엔드)에 이미 선택된 전략이 있어도
  // 로컬만 보면 없는 것처럼 보여 "이 전략으로 시작하기"가 잘못 다시 노출된다. 그래서 로컬에 없으면
  // 이미 조회된 실제 계좌(useTradingData가 채우는 tradingStore.account)의 selected_strategy_id로
  // 한 번 더 확인한다.
  useTradingData();
  const realAccount = useTradingStore((s) => s.account);
  const activeStrategyId = activeAccount?.activeStrategyId ?? realAccount?.selected_strategy_id ?? null;
  // 로그인 사용자인데 App.tsx의 실제 계좌 조회(activeMode 복원)가 아직 끝나지 않았으면, 아직
  // 확정되지 않은 activeStrategyId(=null)를 근거로 "미투자"로 단정하지 않고 CTA를 잠깐 보류한다.
  const activeModeChecked = useInvestmentStore((s) => s.activeModeChecked);
  const ctaPending = isLoggedIn && !activeModeChecked;
  const ctaState: 'start' | 'current' | 'change' =
    !activeStrategyId ? 'start' : activeStrategyId === strategyId ? 'current' : 'change';
  const activeStrategyName = activeStrategyId
    ? (strategyCatalog.find((item) => item.id === activeStrategyId)?.name ?? activeStrategyId)
    : null;
  const [changeConfirmOpen, setChangeConfirmOpen] = useState(false);
  const [changeSubmitting, setChangeSubmitting] = useState(false);
  const [changeError, setChangeError] = useState('');

  // 실제 계좌 전략 변경 API 호출까지 기다린 뒤에만 모달을 닫는다 — 성공 시 이동(Portfolio)은
  // App.tsx의 onConfirmStrategyChange 구현이 처리하고, 실패하면 모달에 에러를 보여주고 계속 띄워둔다.
  const confirmStrategyChange = async () => {
    if (changeSubmitting) return;
    setChangeSubmitting(true);
    setChangeError('');
    try {
      await onConfirmStrategyChange();
      setChangeConfirmOpen(false);
    } catch (e) {
      setChangeError(e instanceof Error ? e.message : '전략을 변경하지 못했어요. 잠시 후 다시 시도해주세요.');
    } finally {
      setChangeSubmitting(false);
    }
  };
  // 백테스트 "결과"는 공개, "다른 기간으로 바꿔보는" interaction만 로그인 필요 — 잠긴 상태에서
  // 다른 기간/직접 설정을 시도하면 즉시 로그인으로 보내지 않고 이 inline 안내를 먼저 보여준다.
  const [showBacktestLoginLock, setShowBacktestLoginLock] = useState(false);
  const [availableRange, setAvailableRange] = useState<BacktestAvailableRange | null>(null);
  const [periods, setPeriods] = useState<BacktestPeriod[]>([]);

  const [periodMode, setPeriodMode] = useState<'preset' | 'custom'>('preset');
  const [presetPeriodId, setPresetPeriodId] = useState('');
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
  const activePeriod: BacktestPeriod | null = useMemo(() => {
    if (periodMode === 'custom' && customPeriod) {
      return { id: 'custom', label: '직접 설정', startDate: customPeriod.startDate, endDate: customPeriod.endDate, description: '' };
    }
    return periods.find((p) => p.id === presetPeriodId) ?? periods[0] ?? null;
  }, [periodMode, customPeriod, presetPeriodId, periods]);

  useEffect(() => {
    let cancelled = false;
    setResultLoading(true);
    setResultError(null);
    getBacktestAvailableRange(strategy.id)
      .then((range) => {
        if (cancelled) return;
        const recommended = getRecommendedPeriods(range);
        setAvailableRange(range);
        setPeriods(recommended);
        setPresetPeriodId((current) => recommended.some((period) => period.id === current) ? current : recommended[0].id);
      })
      .catch((e) => {
        if (!cancelled) {
          setResultError(e instanceof Error ? e.message : '백테스트 가능 기간을 불러오지 못했어요.');
          setResultLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [retryToken]);

  // 전략이 바뀌면(다른 strategyId로 재진입) 기간 선택은 추천 기간 기본값으로 되돌린다
  useEffect(() => {
    if (periods.length === 0) return;
    setPeriodMode('preset');
    setPresetPeriodId(periods[0].id);
    setCustomPeriod(null);
    setCustomPanelOpen(false);
  }, [strategyId, periods]);

  const selectPreset = (id: string) => {
    if (!isLoggedIn && id !== presetPeriodId) { setShowBacktestLoginLock(true); return; }
    setPeriodMode('preset');
    setPresetPeriodId(id);
    setCustomPanelOpen(false);
  };

  const applyCustomPeriod = () => {
    if (!availableRange) return;
    const err = validateCustomPeriod(draftStart, draftEnd, availableRange);
    if (err) { setCustomError(err); return; }
    setCustomError(null);
    setCustomPeriod({ startDate: draftStart, endDate: draftEnd });
    setPeriodMode('custom');
  };

  // 기간이 바뀌면 이전 결과와 AI 설명을 함께 리셋하고 새로 받아온다 — 전략은 그대로 둔다.
  useEffect(() => {
    if (!activePeriod) return;
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
            <button
              onClick={onBack}
              className="self-start text-[15px] font-semibold text-muted transition-colors hover:text-navy"
            >
              ← 투자전략 목록
            </button>
            {showSuitability && recommendation && (
              <span className="text-base font-semibold text-[#3F5222]">✦ 투자성향 적합도 {Math.round(recommendation.score * 100)}%</span>
            )}
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">{strategy.name}</h1>
            <p className="max-w-[820px] text-[19px] leading-8 text-muted">{strategy.description}</p>
            {showSuitability && recommendation && (
              <p className="max-w-[820px] text-[17px] leading-7 text-[#3F5222]">✦ {recommendation.reason}</p>
            )}
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
            {USE_MOCK_BACKTEST && <DemoModeBanner />}
            <div className="flex flex-col gap-2.5">
              <h2 className="text-[26px] font-bold tracking-[-0.025em]">시장이 흔들릴 때, 이 전략은 어땠을까요?</h2>
              <p className="text-[17px] text-muted">
                코로나 폭락, 2022 하락장처럼 실제 시장이 크게 움직였던 시기에 이 전략이 어떻게 움직였는지 확인해보세요.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              {periods.map((p) => {
                const isLocked = !isLoggedIn && p.id !== presetPeriodId;
                return (
                  <button
                    key={p.id}
                    onClick={() => selectPreset(p.id)}
                    className={`group relative flex items-center gap-1.5 rounded-full px-6 py-3.5 text-[17px] font-semibold ${
                      periodMode === 'preset' && p.id === presetPeriodId ? 'bg-lime text-navy' : 'bg-[#F4F6F1] text-muted'
                    }`}
                  >
                    {p.label}
                    {isLocked && <LoginLockBadge />}
                  </button>
                );
              })}
            </div>

            <p className="text-[15px] leading-6 text-muted">
              {activePeriod && <>
                {activePeriod.label} · {fmtDate(activePeriod.startDate)} — {fmtDate(activePeriod.endDate)}
                {periodMode === 'preset' && activePeriod.description && <><br />{activePeriod.description}</>}
              </>}
            </p>

            {showBacktestLoginLock && (
              <div className="flex items-center justify-between gap-6 rounded-[16px] bg-[#F8FCEE] px-7 py-6">
                <div className="flex flex-col gap-1">
                  <span className="text-[15px] font-bold text-[#3F5222]">다른 시장에서도 확인해볼까요?</span>
                  <p className="text-[15px] leading-6 text-[#3F4A43]">
                    로그인하면 기간을 바꿔가며 이 전략을 직접 확인할 수 있어요.
                  </p>
                </div>
                <button
                  onClick={onRequestLoginForBacktest}
                  className="shrink-0 rounded-field bg-lime px-6 py-3.5 text-[15px] font-bold text-navy"
                >
                  다른 기간도 직접 확인하기 →
                </button>
              </div>
            )}

            <button
              onClick={() => {
                if (!isLoggedIn) { setShowBacktestLoginLock(true); return; }
                setCustomPanelOpen((o) => !o);
              }}
              className="group relative inline-flex w-fit items-center gap-1.5 self-start text-[15px] font-semibold text-navy underline"
            >
              원하는 기간이 있나요? 직접 설정 →
              {!isLoggedIn && <LoginLockBadge />}
            </button>

            {customPanelOpen && (
              <div className="flex flex-col gap-3.5 rounded-[16px] bg-[#F8F9F6] p-7">
                <span className="text-[15px] font-bold">직접 기간 설정</span>
                <div className="flex items-center gap-3">
                  <input
                    type="date"
                    value={draftStart}
                    min={availableRange?.minDate}
                    max={availableRange?.maxDate}
                    onChange={(e) => setDraftStart(e.target.value)}
                    className="rounded-field bg-surface px-4 py-3 text-[15px] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
                  />
                  <span className="text-muted">→</span>
                  <input
                    type="date"
                    value={draftEnd}
                    min={availableRange?.minDate}
                    max={availableRange?.maxDate}
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
              <div className="flex gap-8">
                <div className="h-[300px] flex-1 rounded-[14px] bg-[#F4F6F1]" />
                <div className="flex w-[240px] shrink-0 flex-col gap-3">
                  {[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-5 rounded-md bg-[#F0F2ED]" />)}
                </div>
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
              {/* 투자 결과: 그래프(약 75~80%)가 주인공, 주요 지표는 오른쪽 compact summary(고정폭
                 240px)로 축소 — 지표별 개별 카드 대신 얇은 divider로만 구분되는 세로 리스트다.
                 그래프/계산 로직(chartData, LineChart 구성)은 그대로다. */}
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

                <div className="flex gap-8">
                  <div className="h-[300px] min-w-0 flex-1">
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

                  <div className="w-px shrink-0 bg-line" />

                  <div className="flex w-[240px] shrink-0 flex-col justify-center divide-y divide-line">
                    <span className="pb-2.5 text-[13px] font-semibold text-muted">주요 지표</span>
                    <MetricRow label={METRIC_LABELS.cagr} value={signed(result.metrics.cagr)} termKey="cagr" />
                    <MetricRow label={METRIC_LABELS.mdd} value={`${result.metrics.mdd}%`} accent termKey="mdd" />
                    <MetricRow label="변동성" value={`${result.metrics.volatility}%`} termKey="volatility" />
                    {result.metrics.sharpe != null && (
                      <MetricRow label="샤프 지수" value={`${result.metrics.sharpe}`} termKey="sharpe" />
                    )}
                    <MetricRow label="리밸런싱 주기" value={REBALANCE_LABEL[strategy.rebalance_cycle] ?? strategy.rebalance_cycle} />
                  </div>
                </div>
              </section>

              {/* AI 설명은 이 카드 하나로 통합 — 이전에 결과 카드 안에 따로 있던 headline 박스를
                 여기로 옮겨 첫 줄(핵심 요약)로 삼고, 그 아래 한눈에 보면/주의해서 볼 점을 잇는다.
                 headline/overview/caution 전부 backtestApi.fetchAiExplanation()이 실제 백테스트
                 수치를 문장으로 옮긴 값이며, 여기서 숫자를 새로 만들지 않는다. */}
              <section className="flex gap-6 rounded-[20px] bg-accent-soft px-10 py-9">
                <img
                  src={aiLoading ? '/character-thinking.png' : '/character-analyze.png'}
                  alt="물방개"
                  className="h-20 w-20 shrink-0 object-contain"
                />
                <div className="flex flex-1 flex-col gap-4">
                  <span className="text-[22px] font-bold leading-[34px] tracking-[-0.025em]">
                    {aiLoading ? '물방개가 결과를 살펴보고 있어요...' : '물방개가 결과를 쉽게 설명해드릴게요'}
                  </span>
                  {aiError && <p className="text-lg leading-[30px] text-ink-soft">{aiError}</p>}
                  {aiHeadline && (
                    <p className="flex items-start gap-2 text-[21px] font-extrabold leading-[30px] tracking-[-0.02em] text-ink">
                      <span className="mt-0.5 shrink-0 text-lime">✦</span>{aiHeadline}
                    </p>
                  )}
                  {aiOverview && (
                    <div className="flex flex-col gap-1.5">
                      <span className="text-[15px] font-bold text-accent-ink">한눈에 보면</span>
                      <p className="max-w-[760px] text-lg leading-[30px] text-ink-soft">{aiOverview}</p>
                    </div>
                  )}
                  {aiCaution && (
                    <div className="flex flex-col gap-1.5">
                      <span className="text-[15px] font-bold text-accent-ink">주의해서 볼 점</span>
                      <p className="max-w-[760px] text-lg leading-[30px] text-ink-soft">{aiCaution}</p>
                    </div>
                  )}
                </div>
              </section>
            </>
          )}

          {ctaPending && (
            // 로그인 사용자인데 activeMode/실제 계좌 조회가 아직 끝나지 않은 순간 — 이미 투자 중인
            // 사용자에게 "이 전략으로 시작하기"가 잘못(일시적으로) 노출되지 않도록 판단을 보류한다.
            <section className="flex animate-pulse items-center justify-between gap-8 rounded-card bg-navy px-12 py-8">
              <div className="flex flex-col gap-2.5">
                <div className="h-7 w-56 rounded-md bg-white/10" />
                <div className="h-5 w-40 rounded-md bg-white/10" />
              </div>
              <div className="h-14 w-40 shrink-0 rounded-field bg-white/10" />
            </section>
          )}

          {!ctaPending && ctaState === 'start' && (
            <section className="flex items-center justify-between gap-8 rounded-card bg-navy px-12 py-8">
              <span className="text-2xl font-bold tracking-[-0.025em] text-white">이 전략이 마음에 드시나요?</span>
              <div className="flex shrink-0 flex-col items-end gap-2.5">
                <button onClick={onStart} className="rounded-field bg-lime px-9 py-5 text-lg font-bold text-navy">
                  이 전략으로 시작하기 →
                </button>
                {/* "시작하기"가 곧바로 주문 체결이 아니라는 걸 CTA 바로 옆에서 명확히 알려준다 —
                   다음 화면(약관/계좌)을 거치는 동안 실제 편입 종목/전략 구성을 먼저 보여준다.
                   neutral-muted(#B9C2BA)는 navy 배경에서 너무 흐려 보여, 한 단계 밝은 neutral-100로 올림. */}
                <span className="text-[14px] text-neutral-100">다음 단계에서 편입 종목과 전략 구성을 확인할 수 있어요.</span>
              </div>
            </section>
          )}

          {!ctaPending && ctaState === 'current' && (
            <section className="flex items-center justify-between gap-8 rounded-card bg-navy px-12 py-8">
              <div className="flex flex-col gap-2.5">
                <span className="text-2xl font-bold tracking-[-0.025em] text-white">현재 이 전략으로 운용하고 있어요</span>
                <span className="text-[17px] leading-7 text-[#B9C2BA]">
                  투자 현황은{' '}
                  <button onClick={() => onNavigate('portfolio')} className="inline font-semibold text-lime hover:underline">
                    나의 포트폴리오 →
                  </button>
                  {' '}에서 확인할 수 있어요.
                </span>
              </div>
              {/* 행동 버튼이 아니라 상태 표시이므로 lime(액션 색)을 쓰지 않고, 클릭도 불가능한 정보성 배지로 둔다 */}
              <span className="shrink-0 flex items-center gap-2 rounded-full bg-white/10 px-7 py-4 text-base font-bold text-white">
                <span className="text-lime">✓</span> 현재 운용 중
              </span>
            </section>
          )}

          {!ctaPending && ctaState === 'change' && (
            <section className="flex items-center justify-between gap-8 rounded-card bg-navy px-12 py-8">
              <div className="flex flex-col gap-2.5">
                <span className="text-2xl font-bold tracking-[-0.025em] text-white">다른 전략으로 바꿔볼까요?</span>
                <span className="text-[17px] leading-7 text-[#B9C2BA]">
                  지금은 {activeStrategyName}으로 운용 중이에요. 한 계좌에서는 하나의 전략만 운용할 수 있어요.
                </span>
              </div>
              <button
                onClick={() => { setChangeError(''); setChangeConfirmOpen(true); }}
                className="shrink-0 rounded-field bg-lime px-9 py-5 text-lg font-bold text-navy"
              >
                이 전략으로 변경하기 →
              </button>
                        </section>
          )}

          <p className="text-sm leading-[22px] text-subtle">
            ※ 백테스트 결과는 과거 데이터 기반 예시이며 미래 수익을 보장하지 않습니다.
          </p>
        </div>
      </main>

      {changeConfirmOpen && activeStrategyName && (
        <StrategyChangeModal
          currentStrategyName={activeStrategyName}
          nextStrategyName={strategy.name}
          submitting={changeSubmitting}
          error={changeError}
          onCancel={() => { if (!changeSubmitting) setChangeConfirmOpen(false); }}
          onConfirm={() => void confirmStrategyChange()}
        />
      )}
    </div>
  );
}

/** "이 전략으로 변경하기" 확인 모달 — 계좌 하나에는 전략을 하나만 운용할 수 있다는 정책을 확인시키고,
 * 확인 시 실제 계좌 전략 변경 API가 끝날 때까지 기다린다(TermsModal과 동일한 backdrop/카드 스타일 재사용). */
function StrategyChangeModal({
  currentStrategyName, nextStrategyName, submitting, error, onCancel, onConfirm,
}: {
  currentStrategyName: string; nextStrategyName: string; submitting: boolean; error: string;
  onCancel: () => void; onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8" onClick={onCancel}>
      <div className="flex w-[560px] flex-col gap-7 rounded-card bg-surface p-12" onClick={(e) => e.stopPropagation()}>
        <div className="flex flex-col gap-2">
          <h2 className="text-[24px] font-bold tracking-[-0.025em]">{nextStrategyName}으로 변경할까요?</h2>
        </div>

        <div className="flex flex-col gap-3 rounded-[16px] bg-canvas px-7 py-6">
          <div className="flex items-center justify-between">
            <span className="text-[15px] text-muted">현재 전략</span>
            <span className="text-[17px] font-bold text-ink">{currentStrategyName}</span>
          </div>
          <div className="h-px bg-line" />
          <div className="flex items-center justify-between">
            <span className="text-[15px] text-muted">변경할 전략</span>
            <span className="text-[17px] font-bold text-ink">{nextStrategyName}</span>
          </div>
        </div>

        <p className="text-[15px] leading-[24px] text-muted">
          한 계좌에서는 하나의 전략만 운용할 수 있어요.<br />
          변경하면 {currentStrategyName} 대신 {nextStrategyName}으로 운용돼요.
        </p>

        {error && <p className="text-sm text-up">{error}</p>}

        <div className="flex gap-3">
          <button
            onClick={onCancel}
            disabled={submitting}
            className="flex-1 rounded-field bg-[#F4F6F1] py-4 text-base font-semibold text-[#3F4A43] disabled:opacity-60"
          >
            현재 전략 유지하기
          </button>
          <button
            onClick={onConfirm}
            disabled={submitting}
            className="flex-1 rounded-field bg-lime py-4 text-base font-bold text-navy disabled:opacity-60"
          >
            {submitting ? '변경하는 중...' : `${nextStrategyName}으로 변경하기`}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * 비회원 백테스트 interaction 잠금 표시 — 일반 🔒 emoji 대신 FE!N 물방개 얼굴 아이콘(button-pixel.png)을
 * 쓴다. "로그인하면 쓸 수 있는 기능"이라는 뜻으로만 쓰고 에러/경고 의미로는 쓰지 않는다. 부모 버튼에
 * hover가 걸리면(desktop) CSS group-hover로만 tooltip을 보여주는 순수 장식 요소라 자체 클릭 핸들러는
 * 없다 — 실제 클릭 시 안내는 이미 구현된 Inline Login CTA(showBacktestLoginLock)가 담당한다.
 */
function DemoModeBanner() {
  return (
    <div
      role="status"
      className="flex items-center gap-3 rounded-[16px] border-2 border-dashed border-warn bg-warn-soft-2 px-6 py-4 text-[15px] font-bold text-status-amber-text"
    >
      <span className="rounded-full bg-warn px-3 py-1 text-xs font-extrabold text-white">DEMO</span>
      <span>개발용 예시 백테스트입니다. 실제 투자 성과나 미래 수익을 나타내지 않습니다.</span>
    </div>
  );
}

function LoginLockBadge() {
  return (
    <>
      <img src="/button-pixel.png" alt="" className="h-4 w-4 shrink-0 object-contain" />
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 -translate-x-1/2 whitespace-nowrap rounded-md bg-navy px-2.5 py-1.5 text-xs font-medium text-white opacity-0 transition-opacity group-hover:opacity-100"
      >
        로그인 후 이용할 수 있어요
      </span>
    </>
  );
}

/** 주요 지표 compact summary의 한 줄 — 개별 카드 대신 divide-y로만 구분되는 세로 리스트 항목 */
function MetricRow({ label, value, accent, termKey }: { label: string; value: string; accent?: boolean; termKey?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-3 first:pt-2.5 last:pb-0">
      <span className="flex items-center gap-1 text-[13px] text-muted">
        {label}
        {termKey && <TermTooltip label={label} description={METRIC_TERMS[termKey]} />}
      </span>
      <span className={`text-[15px] font-bold ${accent ? 'text-down' : 'text-ink'}`}>{value}</span>
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
