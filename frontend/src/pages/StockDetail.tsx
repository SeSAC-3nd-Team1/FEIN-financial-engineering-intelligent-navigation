import { useEffect, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, PolarAngleAxis, PolarGrid,
  PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { X } from 'lucide-react';
import Header from '../components/Header';
import { AI_EVAL_AXES, ALL_HOLDINGS, HOLD_TOTAL, STOCK_INFO } from '../data/holdings';
import { getStockPriceApi, type PriceResponse } from '../lib/backendApi';
import { TERMS } from '../data/terms';
import { won } from '../lib/validation';
import { useAuthStore } from '../store/authStore';
import { useTradingStore } from '../store/tradingStore';
import type { Screen, TermKey } from '../types';

interface Props {
  index: number;
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
}

type ChartMode = 'simple' | 'detail';
type AiMode = 'bar' | 'radar';

const TIMEFRAMES = [
  { label: '1일', n: 24, vol: 0.6 },
  { label: '1주', n: 14, vol: 1 },
  { label: '3개월', n: 26, vol: 2.2 },
  { label: '6개월', n: 26, vol: 3 },
  { label: '1년', n: 24, vol: 4 },
  { label: '5년', n: 30, vol: 7 },
] as const;

/** 종목·기간을 시드로 쓰는 결정적 시세 (렌더마다 모양이 바뀌지 않는다) */
function priceSeries(seed: number, n: number, vol: number, endChg: number) {
  let x = seed % 233280;
  const steps: number[] = [];
  for (let i = 0; i < n; i++) {
    x = (x * 9301 + 49297) % 233280;
    steps.push((x / 233280 - 0.5) * vol * 2);
  }
  let acc = 0;
  const cum = steps.map((d) => (acc += d));
  const drift = (endChg - cum[cum.length - 1]) / (n - 1);
  return cum.map((v, i) => v + drift * i);
}

export default function StockDetail({ index, userName, onNavigate, onBack }: Props) {
  const holding = ALL_HOLDINGS[index];
  const info = STOCK_INFO[holding.name];
  const token = useAuthStore((state) => state.accessToken);
  const logout = useAuthStore((state) => state.logout);
  const portfolio = useTradingStore((state) => state.portfolio);

  const [chartMode, setChartMode] = useState<ChartMode>('simple');
  const [aiMode, setAiMode] = useState<AiMode>('bar');
  const [tfIndex, setTfIndex] = useState(2);
  const [activeTooltip, setActiveTooltip] = useState<TermKey | null>(null);
  const [livePrice, setLivePrice] = useState<PriceResponse | null>(null);

  useEffect(() => {
    if (!token) return;
    let active = true;
    void getStockPriceApi(info.code, token)
      .then((response) => { if (active) setLivePrice(response); })
      .catch((error: unknown) => {
        if ((error as { status?: number }).status === 401) void logout();
      });
    return () => { active = false; };
  }, [info.code, logout, token]);

  const actualPosition = portfolio?.positions.find((position) => position.stock_code === info.code);
  const currentPrice = Number(livePrice?.price ?? info.price);
  const portfolioWeight = actualPosition && portfolio && Number(portfolio.total_assets) > 0
    ? Number(actualPosition.evaluation_amount) / Number(portfolio.total_assets) * 100
    : holding.pct;
  const portfolioAmount = actualPosition ? Number(actualPosition.evaluation_amount) : (HOLD_TOTAL * holding.pct) / 100;

  const tf = TIMEFRAMES[tfIndex];
  const tfChg = holding.chg * (tfIndex === 0 ? 1 : tfIndex * 2.4);

  const priceData = useMemo(() => {
    const series = priceSeries(Number(info.code) + tfIndex * 977, tf.n, tf.vol, tfChg);
    return series.map((v, i) => ({
      t: i,
      price: Math.round(currentPrice * (1 + v / 100)),
      volume: Math.round(30 + Math.abs(v) * 12),
    }));
  }, [currentPrice, info.code, tfIndex, tf.n, tf.vol, tfChg]);

  const high = Math.max(...priceData.map((d) => d.price));
  const low = Math.min(...priceData.map((d) => d.price));

  /** AI 6축(PER/PBR/ROE/배당수익률/성장성/안정성) — 막대/레이더가 같은 데이터 배열을 공유한다 */
  const aiData = AI_EVAL_AXES.map((subject, i) => ({ subject, score: info.aiEval[i] }));

  const metrics: { label: string; value: string; key: TermKey | null }[] = [
    { label: '시가 총액', value: info.cap, key: null },
    { label: '배당 수익률', value: info.div, key: 'div' },
    { label: 'PBR', value: info.pbr, key: 'pbr' },
    { label: 'PER', value: info.per, key: 'per' },
    { label: 'ROE', value: info.roe, key: 'roe' },
  ];

  const financeMetrics: { label: string; value: string }[] = [
    { label: '부채비율', value: `${info.finance.debtRatio.toFixed(1)}%` },
    { label: '유동비율', value: `${info.finance.currentRatio.toFixed(1)}%` },
    { label: '당좌비율', value: `${info.finance.quickRatio.toFixed(1)}%` },
    { label: '이자보상배율', value: `${info.finance.interestCoverage.toFixed(1)}배` },
  ];

  const term = activeTooltip ? TERMS[activeTooltip] : null;

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-8">
          <button onClick={onBack} className="self-start text-[15px] text-muted">← 보유 종목으로 돌아가기</button>

          {/* 실시간 시세 헤더 */}
          <section className="flex items-end justify-between gap-8">
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-3">
                <h1 className="text-[40px] font-bold tracking-[-0.035em]">{holding.name}</h1>
                <span className="text-[17px] text-subtle">{info.code}</span>
                <span className="rounded-full bg-[#F1F3EE] px-3 py-1.5 text-sm font-semibold text-muted">{holding.sector}</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-[44px] font-bold tracking-[-0.035em]">{won(currentPrice)}</span>
                <span className={`text-xl font-bold ${holding.chg > 0 ? 'text-up' : holding.chg < 0 ? 'text-down' : 'text-subtle'}`}>
                  {holding.chg > 0 ? '+' : ''}{Math.round((currentPrice * holding.chg) / 100).toLocaleString('ko-KR')}원
                  ({holding.chg > 0 ? '+' : ''}{holding.chg.toFixed(1)}%)
                </span>
              </div>
            </div>
            <div className="flex flex-col items-end gap-2">
              <span className="text-[15px] text-muted">내 포트폴리오 비중</span>
              <span className="text-[26px] font-bold tracking-[-0.025em]">{portfolioWeight.toFixed(1)}%</span>
              <span className="text-base text-muted">{won(portfolioAmount)}</span>
            </div>
          </section>

          {/* 차트 */}
          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex items-center justify-between gap-6">
              <div className="flex items-center gap-2 rounded-full bg-[#F4F6F1] p-1.5">
                <Toggle active={chartMode === 'simple'} onClick={() => setChartMode('simple')}>심플하게 보기</Toggle>
                <Toggle active={chartMode === 'detail'} onClick={() => setChartMode('detail')}>자세하게 보기</Toggle>
              </div>
              <div className="flex gap-2">
                {TIMEFRAMES.map((t, i) => (
                  <button
                    key={t.label}
                    onClick={() => setTfIndex(i)}
                    className={`rounded-full px-5 py-3 text-base font-semibold ${
                      i === tfIndex ? 'bg-lime text-navy' : 'bg-[#F4F6F1] text-muted'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-start justify-between gap-8">
              <div className="flex flex-col gap-2">
                <span className="text-base text-muted">{tf.label} 변화</span>
                <span className={`text-[32px] font-bold tracking-[-0.03em] ${tfChg > 0 ? 'text-up' : 'text-down'}`}>
                  {tfChg > 0 ? '+' : ''}{tfChg.toFixed(1)}%
                </span>
              </div>
              {chartMode === 'detail' && (
                <div className="flex gap-8 text-[15px] text-muted">
                  <span>고가 <b className="text-ink">{won(high)}</b></span>
                  <span>저가 <b className="text-ink">{won(low)}</b></span>
                </div>
              )}
            </div>

            <div className="h-[300px] w-full">
              <ResponsiveContainer>
                <LineChart data={priceData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                  {/* 자세히 보기에서만 그리드와 축을 노출한다 */}
                  {chartMode === 'detail' && <CartesianGrid stroke="#F0F2ED" vertical={false} />}
                  {chartMode === 'detail' && <XAxis dataKey="t" hide />}
                  {chartMode === 'detail' && (
                    <YAxis domain={['dataMin', 'dataMax']} tick={{ fill: '#8A948C', fontSize: 13 }} axisLine={false} tickLine={false} width={70} />
                  )}
                  {chartMode === 'detail' && <Tooltip formatter={(v: number) => won(v)} labelFormatter={() => ''} />}
                  <Line
                    type="monotone"
                    dataKey="price"
                    stroke={chartMode === 'detail' ? '#18243A' : '#3E5372'}
                    strokeWidth={chartMode === 'detail' ? 3 : 5}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {chartMode === 'simple' && (
              <p className="text-[17px] leading-7 text-muted">
                {tf.label} 동안 {tfChg > 0 ? '천천히 올랐어요' : '조금 내려왔어요'}. 자세한 고가·저가와 거래량은
                “자세하게 보기”에서 볼 수 있어요.
              </p>
            )}
          </section>

          {/* 재무제표 핵심 지표 */}
          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <h2 className="text-[26px] font-bold tracking-[-0.025em]">재무제표 핵심 지표</h2>
            <div className="grid grid-cols-4 gap-4">
              {financeMetrics.map((m) => (
                <div key={m.label} className="flex flex-col gap-2.5 rounded-[18px] bg-canvas px-6 py-7">
                  <span className="text-[15px] text-muted">{m.label}</span>
                  <span className="text-2xl font-bold tracking-[-0.025em]">{m.value}</span>
                </div>
              ))}
            </div>
          </section>

          {/* 종목 설명 */}
          <section className="flex flex-col gap-4 rounded-card bg-surface p-12">
            <h2 className="text-[26px] font-bold tracking-[-0.025em]">어떤 회사인가요?</h2>
            <p className="text-lg leading-8 text-[#3F4A43] [text-wrap:pretty]">{info.desc}</p>
          </section>

          {/* AI 평가 그래프 */}
          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex items-center justify-between gap-6">
              <div className="flex flex-col gap-2.5">
                <span className="text-base font-semibold text-[#3F5222]">✦ AI 평가</span>
                <h2 className="text-[26px] font-bold tracking-[-0.025em]">이 종목은 내 전략에서 이런 역할이에요</h2>
              </div>
              <div className="flex items-center gap-2 rounded-full bg-[#F4F6F1] p-1.5">
                <Toggle active={aiMode === 'bar'} onClick={() => setAiMode('bar')}>막대그래프</Toggle>
                <Toggle active={aiMode === 'radar'} onClick={() => setAiMode('radar')}>레이더그래프</Toggle>
              </div>
            </div>

            <div className="h-[340px] w-full">
              <ResponsiveContainer>
                {aiMode === 'bar' ? (
                  <BarChart data={aiData} layout="vertical" margin={{ left: 24, right: 24 }}>
                    <CartesianGrid stroke="#F0F2ED" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} tick={{ fill: '#8A948C', fontSize: 13 }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="subject" width={110} tick={{ fill: '#5C665F', fontSize: 15 }} axisLine={false} tickLine={false} />
                    <Bar dataKey="score" fill="#18243A" radius={8} barSize={18} />
                  </BarChart>
                ) : (
                  <RadarChart data={aiData} outerRadius="72%">
                    <PolarGrid stroke="#EDEFEA" />
                    {/* 꼭짓점 라벨: 각 축 이름을 폴리곤 바깥에 렌더 */}
                    <PolarAngleAxis dataKey="subject" tick={{ fill: '#5C665F', fontSize: 15, fontWeight: 600 }} />
                    <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                    <Radar dataKey="score" stroke="#18243A" strokeWidth={2.5} fill="#18243A" fillOpacity={0.12} />
                    <Tooltip />
                  </RadarChart>
                )}
              </ResponsiveContainer>
            </div>

            <div className="flex gap-5 rounded-[20px] bg-[#F8FCEE] px-9 py-8">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-lime text-lg text-navy">✦</div>
              <div className="flex flex-col gap-2.5">
                <span className="text-xl font-bold tracking-[-0.02em]">왜 이 비중으로 담았나요?</span>
                <p className="max-w-[720px] text-lg leading-[30px] text-[#3F4A43]">{holding.why}</p>
              </div>
            </div>
          </section>

          {/* 정보 보기 */}
          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <h2 className="text-[26px] font-bold tracking-[-0.025em]">정보 보기</h2>
            <div className="grid grid-cols-5 gap-4">
              {metrics.map((m) => (
                <div key={m.label} className="flex flex-col gap-2.5 rounded-[18px] bg-canvas px-6 py-7">
                  <div className="flex items-center gap-2">
                    <span className="text-[15px] text-muted">{m.label}</span>
                    {/* "?" 토글 — 같은 항목을 다시 누르면 닫힌다 */}
                    {m.key && (
                      <button
                        aria-label={`${m.label} 설명`}
                        onClick={() => setActiveTooltip((prev) => (prev === m.key ? null : m.key))}
                        className={`h-5 w-5 rounded-full text-xs font-bold ${
                          activeTooltip === m.key ? 'bg-lime text-navy' : 'bg-[#EDEFEA] text-muted'
                        }`}
                      >
                        ?
                      </button>
                    )}
                  </div>
                  <span className="text-2xl font-bold tracking-[-0.025em]">{m.value}</span>
                </div>
              ))}
            </div>

            {term && (
              <div className="flex flex-col gap-4 rounded-[20px] bg-[#F8FCEE] px-10 py-9">
                <div className="flex items-start justify-between gap-6">
                  <div className="flex flex-wrap items-baseline gap-2.5">
                    <span className="text-[22px] font-bold tracking-[-0.02em]">{term.title}</span>
                    <span className="text-[17px] text-muted">{term.ko}</span>
                  </div>
                  <button aria-label="닫기" onClick={() => setActiveTooltip(null)} className="rounded-[9px] bg-surface p-2 text-[#3F4A43]">
                    <X size={16} />
                  </button>
                </div>
                <p className="max-w-[800px] text-lg leading-[30px] text-[#3F4A43]">{term.plain}</p>
                <div className="flex items-center gap-3 rounded-[14px] bg-surface px-6 py-5">
                  <span className="shrink-0 text-[15px] font-semibold text-muted">계산식</span>
                  <span className="text-[17px] font-semibold text-ink">{term.formula}</span>
                </div>
              </div>
            )}
          </section>

          <p className="text-sm leading-[22px] text-subtle">
            ※ 시세와 지표는 예시 데이터이며, 특정 종목의 매매를 권유하지 않습니다.
          </p>
        </div>
      </main>
    </div>
  );
}

function Toggle({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-7 py-3.5 text-[17px] font-semibold ${
        active ? 'bg-surface text-ink shadow-[0_2px_8px_rgba(24,36,58,0.08)]' : 'text-muted'
      }`}
    >
      {children}
    </button>
  );
}
