import { useEffect, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { X } from 'lucide-react';
import Header from '../components/Header';
import {
  AI_AXES, ALL_HOLDINGS as MOCK_HOLDINGS, DECISION_SUMMARY, PAST_DECISIONS,
  PORTFOLIO_TREND, STOCK_CONTRIBUTION, STOCK_INFO,
} from '../data/holdings';
import { STRATEGIES } from '../data/strategies';
import { useTradingData } from '../hooks/useTradingData';
import { getStockPriceApi, type PriceResponse } from '../lib/backendApi';
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
  onSelectStock: (index: number) => void;
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
  { label: '1개월', n: 2 },
  { label: '3개월', n: 3 },
  { label: '1년', n: PORTFOLIO_TREND.length },
  { label: '전체', n: PORTFOLIO_TREND.length },
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
  const orders = useTradingStore((state) => state.orders);
  const executions = useTradingStore((state) => state.executions);
  const accountMissing = useTradingStore((state) => state.accountMissing);
  const isLoading = useTradingStore((state) => state.isLoading);
  const isRefreshing = useTradingStore((state) => state.isRefreshing);
  const isSubmitting = useTradingStore((state) => state.isSubmitting);
  const error = useTradingStore((state) => state.error);
  const orderMessage = useTradingStore((state) => state.orderMessage);
  const placeOrder = useTradingStore((state) => state.placeOrder);
  const ensureAccount = useTradingStore((state) => state.ensureAccount);
  const clearError = useTradingStore((state) => state.clearError);
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

  // 페이지 내 서브뷰 전환 — 현재 앱은 URL 라우터가 없는 화면 상태 머신이라,
  // "지난 판단 돌아보기"는 실제 라우트(`/portfolio/review`) 대신 로컬 뷰 전환으로 구현한다.
  const [view, setView] = useState<'main' | 'review'>('main');

  // ── Power BI 스타일 분석 섹션 상태 ───────────────────────────────
  const [tab, setTab] = useState<AnalyticsTab>('trend');
  const [periodIdx, setPeriodIdx] = useState(2); // 기본값 "1년"
  const [selectedHoldingIdx, setSelectedHoldingIdx] = useState(0);
  const [stockCode, setStockCode] = useState('005930');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [quantity, setQuantity] = useState('1');
  const [quote, setQuote] = useState<PriceResponse | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteError, setQuoteError] = useState<string | null>(null);
  const [lastAttempt, setLastAttempt] = useState<{ signature: string; key: string } | null>(null);

  useEffect(() => {
    if (account?.selected_strategy_id && account.selected_strategy_id !== strategyId) {
      onStrategyChange(account.selected_strategy_id);
    }
  }, [account?.selected_strategy_id, onStrategyChange, strategyId]);

  // 자산 변화 탭: 선택된 기간만큼 최근 구간을 자른다
  const trendData = useMemo(() => PORTFOLIO_TREND.slice(-TREND_PERIODS[periodIdx].n), [periodIdx]);

  // 종목별 기여 탭: 큰 기여 순으로 정렬
  const contributionData = useMemo(
    () => [...STOCK_CONTRIBUTION].sort((a, b) => b.amount - a.amount),
    []
  );
  const topContributor = contributionData[0];

  // 보유 비중 탭은 Portfolio API의 평가금액을 현금 포함 총자산으로 나눈 실제 비중을 사용한다.
  const actualPositions = useMemo(() => {
    if (!portfolio) return [];
    const assets = Number(portfolio.total_assets);
    return portfolio.positions.map((position) => ({
      ...position,
      name: stockName(position.stock_code),
      weight: assets > 0 ? Number(position.evaluation_amount) / assets * 100 : 0,
    }));
  }, [portfolio]);
  const selectedHolding = actualPositions[Math.min(selectedHoldingIdx, Math.max(actualPositions.length - 1, 0))];

  // 위험 분석 탭: 종목별 AI 5축 점수를 보유 비중으로 가중 평균 — StockDetail의 AI_AXES를 그대로 재사용한다
  const totalPct = useMemo(() => MOCK_HOLDINGS.reduce((a, h) => a + h.pct, 0), []);
  const portfolioRisk = useMemo(
    () =>
      AI_AXES.map((subject, i) => {
        const weighted = MOCK_HOLDINGS.reduce((sum, h) => sum + (STOCK_INFO[h.name]?.ai[i] ?? 0) * h.pct, 0);
        return { subject, score: Math.round(weighted / totalPct) };
      }),
    [totalPct]
  );
  const topRiskAxis = portfolioRisk.reduce((a, b) => (b.score > a.score ? b : a));

  if (!portfolio || !account) {
    return (
      <PortfolioState
        userName={userName}
        onNavigate={onNavigate}
        title={isLoading ? '가상계좌를 불러오고 있어요…' : accountMissing ? '아직 가상계좌가 없어요' : !token ? '로그인이 필요해요' : '포트폴리오를 불러오지 못했어요'}
        message={isLoading ? '계좌·주문·체결과 최신 평가정보를 확인하고 있습니다.' : accountMissing ? '전략을 선택하고 가상투자를 시작해주세요.' : error?.message ?? '로그인 상태와 Backend 연결을 확인해주세요.'}
      />
    );
  }

  const totalProfit = Number(portfolio.unrealized_profit) + Number(portfolio.realized_profit);

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
              <span className="text-[40px] font-bold tracking-[-0.035em]">{won(Number(portfolio.total_assets))}</span>
              <span className={`text-xl font-bold ${totalProfit >= 0 ? 'text-up' : 'text-down'}`}>
                총 손익 {totalProfit >= 0 ? '+' : ''}{Math.round(totalProfit).toLocaleString('ko-KR')}원
              </span>
            </div>
            <div className="grid grid-cols-4 gap-3">
              <Fact label="현금잔액" value={won(Number(portfolio.cash_balance))} />
              <Fact label="총 매입금액" value={won(Number(portfolio.total_purchase_amount))} />
              <Fact label="총 평가금액" value={won(Number(portfolio.total_evaluation_amount))} />
              <Fact label="총 수익률" value={`${Number(portfolio.return_rate).toFixed(2)}%`} warn={Number(portfolio.return_rate) < 0} />
            </div>
            {isRefreshing && <span className="text-sm text-subtle">최신 KIS/Redis 가격으로 갱신 중…</span>}
          </section>

          {/* 현재 전략 + 변경 트리거 — Primary 로 강조하지 않는다 */}
          <section className="flex items-center justify-between gap-8 rounded-card bg-surface px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-[15px] text-muted">현재 전략</span>
              <span className="text-2xl font-bold tracking-[-0.025em]">{selectedStrategy.name}</span>
              <span className="text-base text-muted">나와 {selectedStrategy.match}% 잘 맞아요</span>
            </div>
            <button
              onClick={() => setModalOpen(true)}
              className="shrink-0 rounded-field bg-[#F4F6F1] px-7 py-4 text-[17px] font-semibold text-[#3F4A43]"
            >
              전략 변경하기
            </button>
          </section>

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex items-start justify-between gap-8">
              <div className="flex flex-col gap-2">
                <span className="text-[15px] font-semibold text-muted">내부 가상거래 · 시장가</span>
                <h2 className="text-[26px] font-bold tracking-[-0.025em]">매수·매도 주문</h2>
                <p className="text-[16px] text-muted">KIS는 가격만 제공하며 체결과 잔액 변경은 서비스 가상계좌에서 처리됩니다.</p>
              </div>
              <span className="rounded-full bg-[#F4F6F1] px-4 py-2 text-sm font-semibold text-[#3F4A43]">{account.account_name}</span>
            </div>

            <div className="grid grid-cols-[1fr_160px_150px] gap-4">
              <label className="flex flex-col gap-2 text-[15px] font-semibold text-muted">
                종목코드
                <input
                  aria-label="주문 종목코드"
                  value={stockCode}
                  onChange={(event) => { setStockCode(event.target.value.toUpperCase().replace(/[^0-9A-Z]/g, '').slice(0, 12)); setQuote(null); setQuoteError(null); clearError(); }}
                  className="rounded-field bg-canvas px-5 py-4 text-lg font-bold text-ink outline-none focus:ring-2 focus:ring-lime"
                />
              </label>
              <label className="flex flex-col gap-2 text-[15px] font-semibold text-muted">
                주문 방향
                <select aria-label="주문 방향" value={side} onChange={(event) => { setSide(event.target.value as 'BUY' | 'SELL'); clearError(); }} className="rounded-field bg-canvas px-5 py-4 text-lg font-bold text-ink outline-none focus:ring-2 focus:ring-lime">
                  <option value="BUY">매수</option>
                  <option value="SELL">매도</option>
                </select>
              </label>
              <label className="flex flex-col gap-2 text-[15px] font-semibold text-muted">
                수량
                <input
                  aria-label="주문 수량"
                  inputMode="numeric"
                  value={quantity}
                  onChange={(event) => { setQuantity(event.target.value.replace(/\D/g, '').slice(0, 7)); clearError(); }}
                  className="rounded-field bg-canvas px-5 py-4 text-lg font-bold text-ink outline-none focus:ring-2 focus:ring-lime"
                />
              </label>
            </div>

            <div className="flex items-center justify-between gap-5 rounded-[18px] bg-canvas px-7 py-6">
              <div className="flex flex-col gap-1">
                <span className="text-[14px] text-muted">현재가</span>
                <span className="text-xl font-bold">{quote ? won(Number(quote.price)) : '확인 전'}</span>
                {quote && <span className="text-xs text-subtle">{quote.source} · {new Date(quote.as_of).toLocaleString('ko-KR')}</span>}
              </div>
              <div className="flex gap-3">
                <button
                  disabled={quoteLoading || stockCode.length < 6}
                  onClick={async () => {
                    if (!token) return;
                    setQuoteLoading(true);
                    setQuoteError(null);
                    clearError();
                    try { setQuote(await getStockPriceApi(stockCode, token)); }
                    catch (requestError) {
                      setQuoteError(requestError instanceof Error ? requestError.message : '현재가를 조회하지 못했습니다.');
                      if ((requestError as { status?: number }).status === 401) void logout();
                    } finally { setQuoteLoading(false); }
                  }}
                  className="rounded-field bg-surface px-6 py-4 font-semibold text-[#3F4A43] disabled:opacity-50"
                >
                  {quoteLoading ? '조회 중…' : '현재가 확인'}
                </button>
                <button
                  disabled={isSubmitting || stockCode.length < 6 || Number(quantity) <= 0}
                  onClick={async () => {
                    if (!token) return;
                    const signature = `${account.id}:${stockCode}:${side}:${quantity}`;
                    const idempotencyKey = lastAttempt?.signature === signature
                      ? lastAttempt.key
                      : `frontend-${crypto.randomUUID()}`;
                    setLastAttempt({ signature, key: idempotencyKey });
                    try {
                      await placeOrder(token, {
                        account_id: account.id, stock_code: stockCode, side,
                        order_type: 'MARKET', quantity: Number(quantity), idempotency_key: idempotencyKey,
                      });
                      setLastAttempt(null);
                      setQuote(null);
                    } catch (requestError) {
                      if ((requestError as { status?: number }).status === 401) void logout();
                    }
                  }}
                  className={`rounded-field px-8 py-4 font-bold disabled:cursor-not-allowed disabled:opacity-50 ${side === 'BUY' ? 'bg-lime text-navy' : 'bg-navy text-white'}`}
                >
                  {isSubmitting ? '주문 처리 중…' : `${side === 'BUY' ? '매수' : '매도'} 주문`}
                </button>
              </div>
            </div>
            {orderMessage && <p role="status" className="rounded-[14px] bg-[#EAF7EF] px-5 py-4 font-semibold text-[#2E9B65]">{orderMessage}</p>}
            {quoteError && <p role="alert" className="rounded-[14px] bg-[#FFF1F1] px-5 py-4 font-semibold text-down">{quoteError}</p>}
            {error && <p role="alert" className="rounded-[14px] bg-[#FFF1F1] px-5 py-4 font-semibold text-down">{error.message} <span className="text-sm">({error.code})</span></p>}
          </section>

          {/* ── "내 포트폴리오 자세히 보기" — Power BI 임베드 컨테이너 ─────────────
              지금은 4종 그래프를 자체 Recharts 로 렌더링하지만, 컨테이너/탭 구조는
              추후 Power BI iframe·SDK 를 그대로 꽂아 넣을 수 있도록 분리해뒀다. */}
          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex flex-col gap-2.5">
              <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-[#F4F6F1] px-3 py-1.5 text-[11px] font-bold tracking-[0.04em] text-[#3F4A43]">
                POWERBI EMBEDDED · 분석 예시 MOCK
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

                <Insight>
                  {trendData[trendData.length - 1].port >= trendData[trendData.length - 1].kospi
                    ? '시장보다 덜 흔들리면서 더 높은 누적 수익을 내고 있어요.'
                    : '최근 구간에서는 KOSPI가 더 좋았지만, 변동성은 여전히 낮게 유지되고 있어요.'}
                </Insight>
              </div>
            )}

            {tab === 'contribution' && (
              <div className="flex flex-col gap-6">
                <p className="text-[15px] text-subtle">기간 최근 1개월 · 선택한 기간 동안 각 종목이 전체 수익에 얼마나 영향을 줬는지 보여줘요.</p>
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
                <Insight>{topContributor.name}가 수익에 가장 많이 기여했어요.</Insight>
              </div>
            )}

            {tab === 'weight' && (
              actualPositions.length === 0 ? (
                <div className="rounded-[20px] bg-canvas px-9 py-12 text-center text-lg text-muted">매수 후 실제 보유 비중이 표시됩니다.</div>
              ) : (
                <div className="flex items-center gap-14">
                  <div className="relative h-[280px] w-[280px] shrink-0">
                    <ResponsiveContainer>
                      <PieChart>
                        <Pie
                          data={actualPositions}
                          dataKey="weight"
                          nameKey="name"
                          innerRadius="62%"
                          outerRadius="100%"
                          startAngle={90}
                          endAngle={-270}
                          paddingAngle={1}
                          stroke="none"
                          onClick={(_, i) => setSelectedHoldingIdx(i)}
                        >
                          {actualPositions.map((holding, i) => (
                            <Cell
                              key={holding.stock_code}
                              fill={i === selectedHoldingIdx ? '#C6F04D' : DONUT_SHADES[i % DONUT_SHADES.length]}
                              cursor="pointer"
                            />
                          ))}
                        </Pie>
                        <Tooltip formatter={(value: number) => `${Number(value).toFixed(1)}%`} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1">
                      <span className="text-[15px] text-muted">투자자산</span>
                      <span className="text-[26px] font-bold tracking-[-0.03em]">{won(Number(portfolio.total_evaluation_amount))}</span>
                    </div>
                  </div>

                  {selectedHolding && (
                    <div className="flex flex-1 flex-col gap-6">
                      <div className="flex flex-col gap-4 rounded-[20px] bg-canvas px-9 py-8">
                        <div className="flex items-center justify-between">
                          <span className="text-[22px] font-bold tracking-[-0.02em]">{selectedHolding.name}</span>
                          <span className="rounded-full bg-lime px-3.5 py-2 text-sm font-bold text-navy">{selectedHolding.stock_code}</span>
                        </div>
                        <span className="text-[38px] font-bold tracking-[-0.035em]">{selectedHolding.weight.toFixed(1)}%</span>
                        <div className="grid grid-cols-2 gap-5 border-t border-line pt-5">
                          <Fact label="평가금액" value={won(Number(selectedHolding.evaluation_amount))} />
                          <Fact label="수익률" value={`${Number(selectedHolding.return_rate).toFixed(2)}%`} warn={Number(selectedHolding.return_rate) < 0} />
                        </div>
                      </div>
                      <Insight>현금 포함 총자산에서 차지하는 실제 평가 비중입니다.</Insight>
                    </div>
                  )}
                </div>
              )
            )}

            {tab === 'risk' && (
              <div className="flex flex-col gap-6">
                <p className="text-[15px] text-subtle">보유 비중으로 가중 평균한 포트폴리오 전체의 AI 5축 위험 프로파일이에요.</p>
                <div className="h-[320px] w-full">
                  <ResponsiveContainer>
                    <RadarChart data={portfolioRisk} outerRadius="72%">
                      <PolarGrid stroke="#EDEFEA" />
                      <PolarAngleAxis dataKey="subject" tick={{ fill: '#5C665F', fontSize: 15, fontWeight: 600 }} />
                      <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                      <Radar dataKey="score" stroke="#18243A" strokeWidth={2.5} fill="#18243A" fillOpacity={0.12} />
                      <Tooltip />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
                <Insight>{topRiskAxis.subject}이(가) 가장 높은 포트폴리오예요.</Insight>
              </div>
            )}
          </section>

          <section className="flex flex-col gap-5 rounded-card bg-surface p-12">
            <div className="flex items-baseline justify-between">
              <h2 className="text-[26px] font-bold tracking-[-0.025em]">실제 보유종목</h2>
              <span className="text-[15px] text-subtle">{actualPositions.length}개 · Portfolio API 평가 기준</span>
            </div>
            <div className="flex flex-col">
              {actualPositions.length === 0 && (
                <div className="rounded-[18px] bg-canvas px-8 py-10 text-center text-muted">아직 보유종목이 없습니다. 위 주문 영역에서 첫 가상 매수를 시작할 수 있어요.</div>
              )}
              {actualPositions.map((holding, i) => {
                const staticIndex = stockIndex(holding.stock_code);
                return (
                <button
                  key={holding.stock_code}
                  disabled={staticIndex < 0}
                  onClick={() => staticIndex >= 0 && onSelectStock(staticIndex)}
                  className="flex items-center gap-5 border-b border-line py-4 text-left last:border-0 hover:bg-canvas disabled:cursor-default"
                >
                  <span className="w-7 shrink-0 text-[15px] text-subtle">{i + 1}</span>
                  <div className="flex flex-1 flex-col gap-1">
                    <span className="text-[18px] font-semibold tracking-[-0.02em]">{holding.name}</span>
                    <span className="text-[14px] text-subtle">{holding.stock_code} · {holding.quantity.toLocaleString('ko-KR')}주</span>
                  </div>
                  <span className="w-32 text-right text-[15px] text-muted">평균 {won(Number(holding.average_price))}</span>
                  <span className="w-32 text-right text-[16px] font-semibold">{won(Number(holding.evaluation_amount))}</span>
                  <span className={`w-20 text-right text-[16px] font-semibold ${Number(holding.return_rate) > 0 ? 'text-up' : Number(holding.return_rate) < 0 ? 'text-down' : 'text-subtle'}`}>
                    {Number(holding.return_rate) > 0 ? '+' : ''}{Number(holding.return_rate).toFixed(2)}%
                  </span>
                </button>
                );
              })}
            </div>
          </section>

          <section className="grid grid-cols-2 gap-5">
            <TransactionList
              title="최근 주문"
              empty="주문 내역이 없습니다."
              rows={orders.slice(0, 5).map((order) => ({
                id: order.id,
                primary: `${order.stock_code} · ${order.side === 'BUY' ? '매수' : '매도'} ${order.quantity}주`,
                secondary: `${order.status} · ${new Date(order.requested_at).toLocaleString('ko-KR')}`,
                amount: order.requested_price ? won(Number(order.requested_price) * order.quantity) : '-',
              }))}
            />
            <TransactionList
              title="최근 체결"
              empty="체결 내역이 없습니다."
              rows={executions.slice(0, 5).map((execution) => ({
                id: String(execution.id),
                primary: `${execution.stock_code} · ${execution.side === 'BUY' ? '매수' : '매도'} ${execution.quantity}주`,
                secondary: new Date(execution.executed_at).toLocaleString('ko-KR'),
                amount: won(Number(execution.execution_price) * execution.quantity),
              }))}
            />
          </section>

          {/* "내 투자 판단은 어땠을까요?" — 요약 카드. 상세 회고는 "지난 판단 돌아보기"에서 서브뷰로 전환한다 */}
          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <div className="flex flex-col gap-3.5">
              <div className="flex items-center gap-3">
                <h2 className="text-[26px] font-bold tracking-[-0.025em]">내 투자 판단은 어땠을까요?</h2>
                <span className="rounded-full bg-[#F4F6F1] px-3 py-1.5 text-xs font-bold text-muted">MOCK</span>
              </div>
              <p className="text-lg leading-[30px] text-muted">
                AI 제안을 따랐을 때와 내가 선택한 결과를 함께 돌아볼 수 있어요.
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <span className="text-[15px] text-muted">지난 리밸런싱 제안</span>
              <div className="flex items-center gap-3.5 text-[19px] text-[#3F4A43]">
                <span>AI 제안 <b>{PAST_DECISIONS[0].action}</b></span>
                <span className="text-[#A6AFA7]">·</span>
                <span>내 선택 <b>{PAST_DECISIONS[0].choice === '수락' ? '수락함' : '하지 않음 (보류)'}</b></span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2 rounded-[18px] bg-canvas px-8 py-7">
                <span className="text-[15px] text-muted">AI 제안을 따랐다면</span>
                <span className="text-[26px] font-bold tracking-[-0.03em] text-up">{PAST_DECISIONS[0].result}</span>
              </div>
              <div className="flex flex-col gap-2 rounded-[18px] bg-canvas px-8 py-7">
                <span className="text-[15px] text-muted">실제 내 선택</span>
                <span className="text-[26px] font-bold tracking-[-0.03em] text-down">현재 자산 -3,800원</span>
              </div>
            </div>
            <p className="text-[17px] leading-7 text-muted">
              이번에는 AI 제안을 따랐을 때 변동성이 조금 더 낮았어요.
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
                    disabled={isSubmitting}
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
  const maxVol = Math.max(DECISION_SUMMARY.volIfFollowed, DECISION_SUMMARY.volActual);

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <button onClick={onBack} className="self-start text-[15px] text-muted">← 포트폴리오 대시보드로 돌아가기</button>

          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">투자 판단 기록</span>
            <div className="flex items-center gap-3">
              <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">내 투자 판단 돌아보기</h1>
              <span className="rounded-full bg-[#F4F6F1] px-3 py-1.5 text-xs font-bold text-muted">MOCK</span>
            </div>
            <p className="text-[19px] leading-8 text-muted">
              AI 제안과 내가 내린 선택이 이후 포트폴리오에 어떤 차이를 만들었는지 살펴볼 수 있어요.
            </p>
          </section>

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex items-center justify-between">
              <h2 className="text-[22px] font-bold tracking-[-0.025em]">요약 통계</h2>
              <span className="rounded-full bg-[#F4F6F1] px-4 py-2 text-sm font-semibold text-[#3F4A43]">{DECISION_SUMMARY.periodLabel}</span>
            </div>
            <div className="grid grid-cols-3 gap-8">
              <Stat label="AI 제안" value={`${DECISION_SUMMARY.proposed}회`} />
              <Stat label="수락" value={`${DECISION_SUMMARY.accepted}회`} />
              <Stat label="보류" value={`${DECISION_SUMMARY.held}회`} />
            </div>
          </section>

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <h2 className="text-[22px] font-bold tracking-[-0.025em]">AI 제안을 따랐을 때 vs 내 실제 선택</h2>
            <div className="grid grid-cols-2 gap-10">
              <VolBar label="AI 제안을 따랐을 때" value={DECISION_SUMMARY.volIfFollowed} max={maxVol} good />
              <VolBar label="내 실제 선택" value={DECISION_SUMMARY.volActual} max={maxVol} />
            </div>
            <Insight>이번 기간에는 AI 제안을 따랐을 때 포트폴리오의 변동성이 조금 더 낮았어요.</Insight>
          </section>

          <section className="flex flex-col gap-5 rounded-card bg-surface p-12">
            <div className="flex items-baseline justify-between">
              <h2 className="text-[22px] font-bold tracking-[-0.025em]">최근 판단 기록</h2>
              <span className="text-[15px] text-subtle">최근 {PAST_DECISIONS.length}건</span>
            </div>
            <div className="flex flex-col">
              {PAST_DECISIONS.map((d) => (
                <div key={d.date} className="flex items-center gap-6 border-b border-line py-5 last:border-0">
                  <span className="w-24 shrink-0 text-[14px] text-subtle">{d.date}</span>
                  <span className="flex-1 text-[17px] font-semibold text-[#3F4A43]">{d.action}</span>
                  <span
                    className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-bold ${
                      d.choice === '수락' ? 'bg-[#EAF7EF] text-[#2E9B65]' : 'bg-[#F4F6F1] text-muted'
                    }`}
                  >
                    ● {d.choice}
                  </span>
                  <span className="w-48 shrink-0 text-right text-[15px] text-muted">{d.result}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

function stockIndex(stockCode: string): number {
  return MOCK_HOLDINGS.findIndex((holding) => STOCK_INFO[holding.name]?.code === stockCode);
}

function stockName(stockCode: string): string {
  const index = stockIndex(stockCode);
  return index >= 0 ? MOCK_HOLDINGS[index].name : stockCode;
}

function PortfolioState({
  userName, onNavigate, title, message,
}: { userName: string; onNavigate: (s: Screen) => void; title: string; message: string }) {
  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />
      <main className="flex justify-center px-16 pt-20">
        <section className="flex w-[720px] flex-col items-center gap-4 rounded-card bg-surface p-14 text-center">
          <h1 className="text-[30px] font-bold">{title}</h1>
          <p role="status" className="text-lg text-muted">{message}</p>
          <button onClick={() => onNavigate('strategy')} className="mt-3 rounded-field bg-lime px-7 py-4 font-bold text-navy">전략 둘러보기</button>
        </section>
      </main>
    </div>
  );
}

function TransactionList({
  title, empty, rows,
}: {
  title: string;
  empty: string;
  rows: { id: string; primary: string; secondary: string; amount: string }[];
}) {
  return (
    <section className="flex flex-col gap-5 rounded-card bg-surface p-9">
      <h2 className="text-[22px] font-bold">{title}</h2>
      {rows.length === 0 && <p className="text-muted">{empty}</p>}
      <div className="flex flex-col">
        {rows.map((row) => (
          <div key={row.id} className="flex items-center justify-between gap-4 border-b border-line py-4 last:border-0">
            <div className="flex flex-col gap-1">
              <span className="font-semibold">{row.primary}</span>
              <span className="text-xs text-subtle">{row.secondary}</span>
            </div>
            <span className="shrink-0 font-bold">{row.amount}</span>
          </div>
        ))}
      </div>
    </section>
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

function VolBar({ label, value, max, good }: { label: string; value: number; max: number; good?: boolean }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <span className="text-[17px] font-semibold text-[#3F4A43]">{label}</span>
        <span className="text-[22px] font-bold tracking-[-0.02em]">{value.toFixed(1)}%</span>
      </div>
      <div className="h-2.5 rounded-full bg-[#E5E9E3]">
        <div
          className={`h-2.5 rounded-full ${good ? 'bg-lime' : 'bg-[#C3CBC4]'}`}
          style={{ width: `${(value / max) * 100}%` }}
        />
      </div>
      <span className="text-[15px] text-muted">
        변동성 지표가 상대적으로 {good ? '낮은' : '높은'} 편이에요.
      </span>
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
