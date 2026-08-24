import { useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import Header from '../components/Header';
import {
  AI_AXES, ALL_HOLDINGS as MOCK_HOLDINGS, PORTFOLIO_TREND, STOCK_CONTRIBUTION, STOCK_INFO,
} from '../data/holdings';
import { useTradingData } from '../hooks/useTradingData';
import { won } from '../lib/validation';
import { useTradingStore } from '../store/tradingStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  /** "자세히 보기" — 보유종목/AI 제안/거래내역 등 전체 관리 화면(PortfolioDetail)으로 이동한다 */
  onOpenDetail: () => void;
}

/** Power BI 임베드 그래프 변형 4종 — 탭 전환 대상 */
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

/** `/portfolio` — PowerBI Embedded 컨테이너만 담은 페이지. 보유종목·AI제안·거래내역·전략변경 등
 *  나머지 포트폴리오 관리 기능은 전부 "자세히 보기" → PortfolioDetail.tsx(`/portfolio/detail`)로 분리했다.
 *  보유 비중/위험 분석 탭은 실 계좌(useTradingStore.portfolio)가 있으면 그 데이터를, 없으면
 *  MOCK_HOLDINGS 로 대체해 보여준다 — 이 대체 규칙은 PortfolioDetail.tsx 와 동일하게 맞춰뒀다. */
export default function Portfolio({ userName, onNavigate, onOpenDetail }: Props) {
  useTradingData();
  const portfolio = useTradingStore((state) => state.portfolio);

  const ALL_HOLDINGS = useMemo(() => {
    if (!portfolio || portfolio.positions.length === 0) return MOCK_HOLDINGS;
    const assets = Number(portfolio.total_assets);
    return portfolio.positions.map((position) => {
      const matched = MOCK_HOLDINGS.find((holding) => STOCK_INFO[holding.name]?.code === position.stock_code);
      const metadata = matched ?? MOCK_HOLDINGS[0];
      return {
        ...metadata,
        name: matched?.name ?? position.stock_code,
        pct: assets > 0 ? Number(position.evaluation_amount) / assets * 100 : 0,
        chg: Number(position.return_rate),
      };
    });
  }, [portfolio]);

  // ── Power BI 스타일 분석 섹션 상태 ───────────────────────────────
  const [tab, setTab] = useState<AnalyticsTab>('weight');
  const [periodIdx, setPeriodIdx] = useState(2); // 기본값 "1년"
  const [selectedHoldingIdx, setSelectedHoldingIdx] = useState(0);

  // 자산 변화 탭: 선택된 기간만큼 최근 구간을 자른다 — 실 자산 이력 API 가 아직 없어 목업 추이를 그대로 쓴다
  const trendData = useMemo(() => PORTFOLIO_TREND.slice(-TREND_PERIODS[periodIdx].n), [periodIdx]);

  // 종목별 기여 탭: 큰 기여 순으로 정렬 — 역시 목업(실 기여도 산출 API 없음)
  const contributionData = useMemo(
    () => [...STOCK_CONTRIBUTION].sort((a, b) => b.amount - a.amount),
    []
  );
  const topContributor = contributionData[0];

  // 보유 비중 탭: 선택된 종목의 현재 비중 vs 전략 목표 비중
  const safeSelectedIndex = Math.min(selectedHoldingIdx, Math.max(ALL_HOLDINGS.length - 1, 0));
  const selectedHolding = ALL_HOLDINGS[safeSelectedIndex];
  const targetPct = selectedHolding.target ?? selectedHolding.pct;
  const weightDiff = Math.round((selectedHolding.pct - targetPct) * 10) / 10;

  // 위험 분석 탭: 종목별 AI 5축 점수를 보유 비중으로 가중 평균 — StockDetail의 AI_AXES를 그대로 재사용한다
  const totalPct = useMemo(() => ALL_HOLDINGS.reduce((a, h) => a + h.pct, 0), [ALL_HOLDINGS]);
  const portfolioRisk = useMemo(
    () =>
      AI_AXES.map((subject, i) => {
        const weighted = ALL_HOLDINGS.reduce((sum, h) => sum + (STOCK_INFO[h.name]?.ai[i] ?? 0) * h.pct, 0);
        return { subject, score: totalPct > 0 ? Math.round(weighted / totalPct) : 0 };
      }),
    [ALL_HOLDINGS, totalPct]
  );
  const topRiskAxis = portfolioRisk.reduce((a, b) => (b.score > a.score ? b : a));

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          {/* ── PowerBI Embedded 컨테이너 — 이 페이지의 유일한 콘텐츠 ─────────────
              지금은 4종 그래프를 자체 Recharts 로 렌더링하지만, 컨테이너/탭 구조는
              추후 Power BI iframe·SDK 를 그대로 꽂아 넣을 수 있도록 분리해뒀다. */}
          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex items-start justify-between gap-6">
              <div className="flex flex-col gap-2.5">
                <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-[#F4F6F1] px-3 py-1.5 text-[11px] font-bold tracking-[0.04em] text-[#3F4A43]">
                  POWERBI EMBEDDED
                </span>
                <h1 className="text-[32px] font-bold leading-[46px] tracking-[-0.03em]">나의 포트폴리오</h1>
                <p className="text-[17px] text-muted">여기부터는 데이터를 직접 탐색할 수 있어요.</p>
              </div>
              {/* "자세히 보기" — 클릭 시 보유종목/AI제안/거래내역 등 전체 관리 화면(portfolio-detail)으로 라우팅한다 */}
              <button
                onClick={onOpenDetail}
                className="shrink-0 rounded-field bg-lime px-7 py-4 text-[17px] font-bold text-navy"
              >
                자세히 보기 →
              </button>
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
                      <Fact label="목표" value={`${targetPct.toFixed(1)}%`} />
                      <Fact label="차이" value={`${weightDiff > 0 ? '+' : ''}${weightDiff.toFixed(1)}%p`} warn={weightDiff > 0} />
                    </div>
                  </div>
                  <Insight>
                    {weightDiff > 0
                      ? `${selectedHolding.name} 비중이 목표보다 높아요.`
                      : weightDiff < 0
                        ? `${selectedHolding.name} 비중이 목표보다 낮아요.`
                        : `${selectedHolding.name} 비중이 목표와 일치해요.`}
                  </Insight>
                </div>
              </div>
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

function Insight({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-4 rounded-[18px] bg-[#F8FCEE] px-8 py-6">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-lime text-base text-navy">✦</div>
      <p className="pt-0.5 text-[17px] leading-7 text-[#3F4A43]">{children}</p>
    </div>
  );
}
