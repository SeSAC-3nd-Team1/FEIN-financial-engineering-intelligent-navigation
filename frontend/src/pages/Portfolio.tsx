import { useEffect, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { X } from 'lucide-react';
import Header from '../components/Header';
import { STRATEGIES } from '../data/strategies';
import { useTradingData } from '../hooks/useTradingData';
import { getPortfolioHistoryApi, type PortfolioHistoryResponse } from '../lib/backendApi';
import { buildPortfolioHoldings } from '../lib/portfolioModel';
import { won } from '../lib/validation';
import { useAuthStore } from '../store/authStore';
import { useTradingStore } from '../store/tradingStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  /** 모달에서 선택·표시되는 현재 전략 id — RiskResult/StrategyDetail 과 동일한 STRATEGIES.id 를 그대로 쓴다
   *  (과거엔 이 화면만 별도의 표시용 전략 이름 상태를 들고 있어, 다른 화면에서 고른 전략과 어긋나는 문제가 있었다) */
  strategyId: string;
  onStrategyChange: (id: string) => void;
  onNavigate: (s: Screen) => void;
  onSelectStock: (stockCode: string) => void;
  /** 모달의 "다시 진단하기" — 투자성향 진단으로 되돌린다 */
  onRediagnose: () => void;
  onBack: () => void;
}

/** Power BI 임베드 그래프 변형 4종 — "내 포트폴리오 자세히 보기" 탭 전환 대상 */
type AnalyticsTab = 'trend' | 'contribution' | 'weight' | 'risk';
const ANALYTICS_TABS: { id: AnalyticsTab; label: string }[] = [
  { id: 'trend', label: '자산 변화' },
  { id: 'contribution', label: '종목별 기여' },
  { id: 'weight', label: '보유 비중' },
  { id: 'risk', label: '위험 분석' },
];

// n:1 이면 라인 차트에 점이 하나뿐이라(dot={false}) 아무것도 안 보인다 — 최소 2개 포인트를 보장한다.
const TREND_PERIODS = [
  { label: '1개월', period: '1M' },
  { label: '3개월', period: '3M' },
  { label: '1년', period: '1Y' },
  { label: '전체', period: 'ALL' },
] as const;

/** 도넛(보유 비중) 색 — 선택된 조각만 라임, 나머지는 순환 셰이드 */
const DONUT_SHADES = ['#18243A', '#2E4160', '#4A5F80', '#6C819E', '#8FA0B4', '#C3CBC4'];

export default function Portfolio({
  userName, strategyId, onStrategyChange, onNavigate, onSelectStock, onRediagnose, onBack,
}: Props) {
  const token = useTradingData();
  const logout = useAuthStore((state) => state.logout);
  const account = useTradingStore((state) => state.account);
  const portfolio = useTradingStore((state) => state.portfolio);
  const ensureAccount = useTradingStore((state) => state.ensureAccount);

  // 전략 변경 모달 상태
  const [isModalOpen, setModalOpen] = useState(false);
  // strategyId 로부터 표시용 전략 객체(이름/나와 맞는 정도 등)를 파생시킨다 — STRATEGIES 가 유일한 출처
  const selectedStrategy = STRATEGIES.find((s) => s.id === strategyId) ?? STRATEGIES[0];
  const setSelectedStrategy = async (nextStrategyId: string) => {
    if (!token) return;
    try {
      await ensureAccount(token, nextStrategyId);
      onStrategyChange(nextStrategyId);
      setModalOpen(false);
    } catch (requestError) {
      if ((requestError as { status?: number }).status === 401) void logout();
    }
  };

  useEffect(() => {
    if (account?.selected_strategy_id && account.selected_strategy_id !== strategyId) {
      onStrategyChange(account.selected_strategy_id);
    }
  }, [account?.selected_strategy_id, onStrategyChange, strategyId]);

  const HOLD_TOTAL = portfolio ? Number(portfolio.total_assets) : null;
  const ALL_HOLDINGS = useMemo(() => buildPortfolioHoldings(portfolio), [portfolio]);

  // 페이지 내 서브뷰 전환 — 현재 앱은 URL 라우터가 없는 화면 상태 머신이라,
  // "지난 판단 돌아보기"는 실제 라우트(`/portfolio/review`) 대신 로컬 뷰 전환으로 구현한다.
  const [view, setView] = useState<'main' | 'review'>('main');

  // ── Power BI 스타일 분석 섹션 상태 ───────────────────────────────
  const [tab, setTab] = useState<AnalyticsTab>('trend');
  const [periodIdx, setPeriodIdx] = useState(2); // 기본값 "1년"
  const [selectedHoldingIdx, setSelectedHoldingIdx] = useState(0);
  const [history, setHistory] = useState<PortfolioHistoryResponse | null>(null);

  useEffect(() => {
    if (!token || !account) {
      setHistory(null);
      return;
    }
    void getPortfolioHistoryApi(account.id, TREND_PERIODS[periodIdx].period, token)
      .then(setHistory)
      .catch(() => setHistory(null));
  }, [account, periodIdx, token]);

  /** 오늘 손익 = 평가금액 × 등락률. 요약과 종목 행이 같은 계산을 쓴다 */
  const gains = useMemo(
    () => ALL_HOLDINGS.map((h) => {
      const position = portfolio?.positions.find((item) => item.stock_code === h.stockCode);
      return {
        ...h,
        gain: position?.today_profit == null ? 0 : Number(position.today_profit),
      };
    }),
    [ALL_HOLDINGS, portfolio]
  );
  const todayTotal = portfolio?.today_profit == null ? null : Number(portfolio.today_profit);

  // 자산 변화 탭: 선택된 기간만큼 최근 구간을 자른다
  const trendData = useMemo(() => (history?.items ?? []).map((item) => ({
    label: item.date,
    port: Number(item.portfolio_return_rate),
    kospi: item.benchmark_return_rate == null ? null : Number(item.benchmark_return_rate),
  })), [history]);

  // 종목별 기여 탭: 큰 기여 순으로 정렬
  const contributionData = useMemo(
    () => (portfolio?.contributions ?? []).map((item) => ({
      name: item.stock_name ?? item.stock_code,
      amount: Number(item.amount),
    })).sort((a, b) => b.amount - a.amount),
    [portfolio?.contributions]
  );
  const topContributor = contributionData[0];

  // 보유 비중 탭: 선택된 종목의 현재 비중 vs 전략 목표 비중
  const safeSelectedIndex = Math.min(selectedHoldingIdx, Math.max(ALL_HOLDINGS.length - 1, 0));
  const selectedHolding = ALL_HOLDINGS[safeSelectedIndex];
  const selectedProposal = portfolio?.rebalancing_proposals.find(
    (item) => item.stock_code === selectedHolding?.stockCode,
  );
  const targetPct = selectedProposal == null ? null : Number(selectedProposal.target_weight);
  const weightDiff = selectedProposal == null ? null : Number(selectedProposal.weight_diff);

  if (view === 'review') {
    return (
      <ReviewView
        userName={userName}
        onNavigate={onNavigate}
        onBack={() => setView('main')}
      />
    );
  }

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <button onClick={onBack} className="self-start text-[15px] text-muted">← 대시보드로 돌아가기</button>

          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">나의 포트폴리오</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
              {userName}님의 투자는<br />오늘도 전략대로 움직이고 있어요.
            </h1>
            <div className="flex items-baseline gap-4">
              <span className="text-[40px] font-bold tracking-[-0.035em]">{HOLD_TOTAL == null ? '-' : won(HOLD_TOTAL)}</span>
              <span className="text-xl font-bold text-up">
                {todayTotal == null ? '오늘 -' : `오늘 ${todayTotal >= 0 ? '+' : ''}${Math.round(todayTotal).toLocaleString('ko-KR')}원`}
              </span>
            </div>
          </section>

          {/* 현재 전략 + 변경 트리거 — Primary 로 강조하지 않는다 */}
          <section className="flex items-center justify-between gap-8 rounded-card bg-surface px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-[15px] text-muted">현재 전략</span>
              <span className="text-2xl font-bold tracking-[-0.025em]">{selectedStrategy.name}</span>
              <span className="text-base text-muted">전략 적합도 -</span>
            </div>
            <button
              onClick={() => setModalOpen(true)}
              className="shrink-0 rounded-field bg-[#F4F6F1] px-7 py-4 text-[17px] font-semibold text-[#3F4A43]"
            >
              전략 변경하기
            </button>
          </section>

          {/* ── "내 포트폴리오 자세히 보기" — Power BI 임베드 컨테이너 ─────────────
              지금은 4종 그래프를 자체 Recharts 로 렌더링하지만, 컨테이너/탭 구조는
              추후 Power BI iframe·SDK 를 그대로 꽂아 넣을 수 있도록 분리해뒀다. */}
          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex flex-col gap-2.5">
              <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-[#F4F6F1] px-3 py-1.5 text-[11px] font-bold tracking-[0.04em] text-[#3F4A43]">
                POWERBI EMBEDDED
              </span>
              <h2 className="text-[26px] font-bold tracking-[-0.025em]">내 포트폴리오 자세히 보기</h2>
              <p className="text-[17px] text-muted">여기부터는 데이터를 직접 탐색할 수 있어요.</p>
            </div>

            {/* 그래프 변형 스위처 — 자산변화(Line) / 종목별기여(Bar) / 보유비중(Donut) / 위험분석(Radar) */}
            <div className="flex flex-wrap gap-2 border-b border-line pb-1">
              {ANALYTICS_TABS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`rounded-t-[10px] px-5 py-3 text-[15px] font-semibold ${
                    tab === t.id ? 'bg-canvas text-ink' : 'text-muted'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {tab === 'trend' && (
              <div className="flex flex-col gap-6">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="flex gap-2">
                    {TREND_PERIODS.map((p, i) => (
                      <button
                        key={p.label}
                        onClick={() => setPeriodIdx(i)}
                        className={`rounded-full px-5 py-2.5 text-[15px] font-semibold ${
                          i === periodIdx ? 'bg-lime text-navy' : 'bg-[#F4F6F1] text-muted'
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                  <span className="text-[15px] text-subtle">비교 기준 <b className="text-[#3F4A43]">KOSPI</b></span>
                </div>

                <div className="h-[300px] w-full">
                  <ResponsiveContainer>
                    <LineChart data={trendData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke="#F0F2ED" vertical={false} />
                      <XAxis dataKey="label" tick={{ fill: '#8A948C', fontSize: 12 }} axisLine={false} tickLine={false} />
                      <YAxis
                        tick={{ fill: '#8A948C', fontSize: 13 }}
                        axisLine={false}
                        tickLine={false}
                        width={52}
                        tickFormatter={(v: number) => `${v}%`}
                      />
                      <Tooltip formatter={(v: number) => `${v}%`} />
                      <Legend iconType="plainline" wrapperStyle={{ fontSize: 15, color: '#5C665F' }} />
                      <Line type="monotone" dataKey="kospi" name="KOSPI" stroke="#C3CBC4" strokeWidth={3.5} dot={false} />
                      <Line type="monotone" dataKey="port" name="내 포트폴리오" stroke="#18243A" strokeWidth={5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                <Insight>{trendData.length < 2 ? '실제 자산 스냅샷이 쌓이면 KOSPI와 수익률을 비교할 수 있어요.' : '실제 계좌 자산 변화와 KOSPI 누적 수익률을 비교한 결과예요.'}</Insight>
              </div>
            )}

            {tab === 'contribution' && (
              <div className="flex flex-col gap-6">
                <p className="text-[15px] text-subtle">오늘 · 전일 종가 대비 각 종목이 오늘 손익에 얼마나 영향을 줬는지 보여줘요.</p>
                <div className="h-[260px] w-full">
                  <ResponsiveContainer>
                    <BarChart data={contributionData} layout="vertical" margin={{ left: 24, right: 24 }}>
                      <CartesianGrid stroke="#F0F2ED" horizontal={false} />
                      <XAxis type="number" tickFormatter={(v: number) => won(v)} tick={{ fill: '#8A948C', fontSize: 12 }} axisLine={false} tickLine={false} />
                      <YAxis type="category" dataKey="name" width={100} tick={{ fill: '#5C665F', fontSize: 15 }} axisLine={false} tickLine={false} />
                      <Tooltip formatter={(v: number) => won(v)} />
                      <Bar dataKey="amount" radius={8} barSize={20}>
                        {contributionData.map((d) => (
                          <Cell key={d.name} fill={d.amount >= 0 ? '#18243A' : '#C24A4A'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <Insight>{topContributor ? `${topContributor.name}가 오늘 수익에 가장 많이 기여했어요.` : '당일 기여도를 계산할 수 있는 시세가 아직 없어요.'}</Insight>
              </div>
            )}

            {tab === 'weight' && selectedHolding && (
              <div className="flex items-center gap-14">
                <div className="relative h-[280px] w-[280px] shrink-0">
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie
                        data={ALL_HOLDINGS}
                        dataKey="pct"
                        nameKey="name"
                        innerRadius="62%"
                        outerRadius="100%"
                        startAngle={90}
                        endAngle={-270}
                        paddingAngle={1}
                        stroke="none"
                        onClick={(_, i) => setSelectedHoldingIdx(i)}
                      >
                        {ALL_HOLDINGS.map((h, i) => (
                          <Cell
                            key={h.name}
                            fill={i === selectedHoldingIdx ? '#C6F04D' : DONUT_SHADES[i % DONUT_SHADES.length]}
                            cursor="pointer"
                          />
                        ))}
                      </Pie>
                      <Tooltip formatter={(v: number) => `${(v as number).toFixed(1)}%`} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1">
                    <span className="text-[15px] text-muted">총 자산</span>
                    <span className="text-[26px] font-bold tracking-[-0.03em]">100%</span>
                  </div>
                </div>

                <div className="flex flex-1 flex-col gap-6">
                  <div className="flex flex-col gap-4 rounded-[20px] bg-canvas px-9 py-8">
                    <div className="flex items-center justify-between">
                      <span className="text-[22px] font-bold tracking-[-0.02em]">{selectedHolding.name}</span>
                      <span className="rounded-full bg-lime px-3.5 py-2 text-sm font-bold text-navy">선택됨</span>
                    </div>
                    <span className="text-[38px] font-bold tracking-[-0.035em]">{selectedHolding.pct.toFixed(1)}%</span>
                    <div className="flex gap-10 border-t border-line pt-5">
                      <Fact label="목표" value={targetPct == null ? '-' : `${targetPct.toFixed(1)}%`} />
                      <Fact label="차이" value={weightDiff == null ? '-' : `${weightDiff > 0 ? '+' : ''}${weightDiff.toFixed(1)}%p`} warn={weightDiff != null && weightDiff > 0} />
                    </div>
                  </div>
                  <Insight>
                    {weightDiff == null
                      ? '이 전략의 실제 목표 비중 데이터가 아직 없어요.'
                      : weightDiff > 0
                      ? `${selectedHolding.name} 비중이 목표보다 높아요.`
                      : weightDiff < 0
                        ? `${selectedHolding.name} 비중이 목표보다 낮아요.`
                        : `${selectedHolding.name} 비중이 목표와 일치해요.`}
                  </Insight>
                </div>
              </div>
            )}

            {tab === 'weight' && !selectedHolding && (
              <div className="flex h-[280px] items-center justify-center rounded-[20px] bg-canvas text-lg text-muted">보유 종목이 아직 없어요.</div>
            )}

            {tab === 'risk' && (
              <div className="flex flex-col gap-6">
                <p className="text-[15px] text-subtle">AI 5축 위험 점수는 실제 feature 산식과 기록 데이터가 준비된 뒤 제공됩니다.</p>
                <div className="flex h-[320px] items-center justify-center rounded-[20px] bg-canvas text-lg text-muted">위험 분석 데이터가 아직 없어요.</div>
                <Insight>신뢰성 있게 계산할 수 없는 점수는 임의 값으로 표시하지 않아요.</Insight>
              </div>
            )}
          </section>

          <section className="flex flex-col gap-5 rounded-card bg-surface p-12">
            <div className="flex items-baseline justify-between">
              <h2 className="text-[26px] font-bold tracking-[-0.025em]">전체 {gains.length}개 종목</h2>
              <span className="text-[15px] text-subtle">종목을 누르면 상세 정보를 볼 수 있어요</span>
            </div>
            <div className="flex flex-col">
              {gains.map((h, i) => {
                return (
                <button
                  key={h.name}
                  onClick={() => h.stockCode && onSelectStock(h.stockCode)}
                  className="flex items-center gap-5 border-b border-line py-4 text-left last:border-0 hover:bg-canvas"
                >
                  <span className="w-7 shrink-0 text-[15px] text-subtle">{i + 1}</span>
                  <div className="flex flex-1 flex-col gap-1">
                    <span className="text-[18px] font-semibold tracking-[-0.02em]">{h.name}</span>
                    <span className="text-[14px] text-subtle">{h.sector}</span>
                  </div>
                  <span className="w-24 text-right text-[17px] font-bold">{h.pct.toFixed(1)}%</span>
                  <span className="w-32 text-right text-[16px] text-muted">{HOLD_TOTAL == null ? '-' : won((HOLD_TOTAL * h.pct) / 100)}</span>
                  <span className={`w-20 text-right text-[16px] font-semibold ${h.chg != null && h.chg > 0 ? 'text-up' : h.chg != null && h.chg < 0 ? 'text-down' : 'text-subtle'}`}>
                    {h.chg == null ? '-' : `${h.chg > 0 ? '+' : ''}${h.chg.toFixed(1)}%`}
                  </span>
                </button>
                );
              })}
            </div>
          </section>

          {/* "내 투자 판단은 어땠을까요?" — 요약 카드. 상세 회고는 "지난 판단 돌아보기"에서 서브뷰로 전환한다 */}
          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <div className="flex flex-col gap-3.5">
              <h2 className="text-[26px] font-bold tracking-[-0.025em]">내 투자 판단은 어땠을까요?</h2>
              <p className="text-lg leading-[30px] text-muted">
                AI 제안을 따랐을 때와 내가 선택한 결과를 함께 돌아볼 수 있어요.
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <span className="text-[15px] text-muted">지난 리밸런싱 제안</span>
              <div className="flex items-center gap-3.5 text-[19px] text-[#3F4A43]">
                <span>AI 제안 <b>-</b></span>
                <span className="text-[#A6AFA7]">·</span>
                <span>내 선택 <b>-</b></span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2 rounded-[18px] bg-canvas px-8 py-7">
                <span className="text-[15px] text-muted">AI 제안을 따랐다면</span>
                <span className="text-[26px] font-bold tracking-[-0.03em]">-</span>
              </div>
              <div className="flex flex-col gap-2 rounded-[18px] bg-canvas px-8 py-7">
                <span className="text-[15px] text-muted">실제 내 선택</span>
                <span className="text-[26px] font-bold tracking-[-0.03em]">-</span>
              </div>
            </div>
            <p className="text-[17px] leading-7 text-muted">
              실제 판단 이력이 쌓이면 결과를 비교할 수 있어요.
            </p>
            {/* 트리거: 클릭 시 로컬 view state 를 'review' 로 전환해 PDF Page 5 레이아웃(ReviewView)을 렌더링한다 */}
            <button
              onClick={() => setView('review')}
              className="self-start text-base font-semibold text-navy"
            >
              지난 판단 돌아보기 →
            </button>
          </section>
        </div>
      </main>

      {/* 전략 변경 모달 — 현재 전략만 라임 테두리로 강조 */}
      {isModalOpen && (
        <div className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8" onClick={() => setModalOpen(false)}>
          <div className="flex w-[640px] flex-col gap-7 rounded-card bg-surface p-12" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-6">
              <div className="flex flex-col gap-2.5">
                <h2 className="text-[28px] font-bold tracking-[-0.03em]">어떤 전략으로 운용할까요?</h2>
                <p className="text-[17px] leading-7 text-muted">전략은 언제든 바꿀 수 있어요.</p>
              </div>
              <button aria-label="닫기" onClick={() => setModalOpen(false)} className="rounded-[9px] bg-canvas p-2 text-muted">
                <X size={18} />
              </button>
            </div>

            <div className="flex flex-col gap-3">
              {STRATEGIES.map((s) => {
                const active = s.id === selectedStrategy.id;
                return (
                  <button
                    key={s.id}
                    onClick={() => void setSelectedStrategy(s.id)}
                    className={`flex items-center justify-between rounded-[20px] px-8 py-7 text-left ${
                      active ? 'bg-[#F8FCEE] shadow-[0_0_0_2px_#C6F04D_inset]' : 'bg-canvas shadow-[0_0_0_1px_#E5E9E3_inset]'
                    }`}
                  >
                    <span className="text-[22px] font-bold tracking-[-0.02em]">{s.name}</span>
                    {active && (
                      <span className="rounded-full bg-lime px-3.5 py-2 text-sm font-bold text-navy">현재 전략</span>
                    )}
                  </button>
                );
              })}
            </div>

            <button
              onClick={onRediagnose}
              className="rounded-field bg-[#F4F6F1] py-5 text-[17px] font-semibold text-[#3F4A43]"
            >
              다시 진단하기
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** PDF Page 5 — "내 투자 판단 돌아보기" 서브뷰. 라우터가 생기면 `/portfolio/review` 로 그대로 옮길 수 있다 */
function ReviewView({ userName, onNavigate, onBack }: { userName: string; onNavigate: (s: Screen) => void; onBack: () => void }) {
  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <button onClick={onBack} className="self-start text-[15px] text-muted">← 포트폴리오 대시보드로 돌아가기</button>

          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">투자 판단 기록</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">내 투자 판단 돌아보기</h1>
            <p className="text-[19px] leading-8 text-muted">
              AI 제안과 내가 내린 선택이 이후 포트폴리오에 어떤 차이를 만들었는지 살펴볼 수 있어요.
            </p>
          </section>

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex items-center justify-between">
              <h2 className="text-[22px] font-bold tracking-[-0.025em]">요약 통계</h2>
              <span className="rounded-full bg-[#F4F6F1] px-4 py-2 text-sm font-semibold text-[#3F4A43]">-</span>
            </div>
            <div className="grid grid-cols-3 gap-8">
              <Stat label="AI 제안" value="-" />
              <Stat label="수락" value="-" />
              <Stat label="보류" value="-" />
            </div>
          </section>

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <h2 className="text-[22px] font-bold tracking-[-0.025em]">AI 제안을 따랐을 때 vs 내 실제 선택</h2>
            <div className="flex h-32 items-center justify-center rounded-[20px] bg-canvas text-lg text-muted">비교할 실제 판단 이력이 아직 없어요.</div>
            <Insight>실제 기록이 없는 결과를 임의 값으로 표시하지 않아요.</Insight>
          </section>

          <section className="flex flex-col gap-5 rounded-card bg-surface p-12">
            <div className="flex items-baseline justify-between">
              <h2 className="text-[22px] font-bold tracking-[-0.025em]">최근 판단 기록</h2>
              <span className="text-[15px] text-subtle">최근 0건</span>
            </div>
            <div className="flex flex-col">
              <div className="py-8 text-center text-[17px] text-muted">아직 기록된 리밸런싱 판단이 없어요.</div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

function Fact({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[15px] text-muted">{label}</span>
      <span className={`text-xl font-bold ${warn ? 'text-warn' : ''}`}>{value}</span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[15px] text-muted">{label}</span>
      <span className="text-[32px] font-bold tracking-[-0.03em]">{value}</span>
    </div>
  );
}

function Insight({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-4 rounded-[18px] bg-[#F8FCEE] px-8 py-6">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-lime text-base text-navy">✦</div>
      <p className="pt-0.5 text-[17px] leading-7 text-[#3F4A43]">{children}</p>
    </div>
  );
}
