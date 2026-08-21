import { useState } from 'react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import Header from '../components/Header';
import { SCENARIOS, STRATEGIES } from '../data/strategies';
import type { Screen } from '../types';

interface Props {
  strategyId: string;
  userName: string;
  onNavigate: (s: Screen) => void;
  onStart: () => void;
  onOpenBacktest: () => void;
}

/** 03 전략 상세 — 구간을 바꿔가며 내 돈이 어땠을지 체험하는 Playground */
export default function StrategyDetail({ strategyId, userName, onNavigate, onStart, onOpenBacktest }: Props) {
  const strategy = STRATEGIES.find((s) => s.id === strategyId) ?? STRATEGIES[0];
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);

  const scenario = SCENARIOS.find((s) => s.id === scenarioId)!;
  // 차트 데이터: 전략 vs KOSPI 를 같은 배열에 담아 한 번에 그린다
  const chartData = scenario.strat.map((v, i) => ({ t: i, 내전략: v, KOSPI: scenario.kospi[i] }));
  const endValue = Math.round(scenario.amount * (1 + scenario.stratEnd / 100));
  const diff = endValue - scenario.amount;

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

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex flex-col gap-2.5">
              <h2 className="text-[26px] font-bold tracking-[-0.025em]">언제를 골라볼까요?</h2>
              <p className="text-[17px] text-muted">1,000만원을 넣었다고 가정하고, 구간을 바꿔가며 결과를 볼 수 있어요.</p>
            </div>

            <div className="flex flex-wrap gap-3">
              {SCENARIOS.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setScenarioId(s.id)}
                  className={`rounded-full px-6 py-3.5 text-[17px] font-semibold ${
                    s.id === scenarioId ? 'bg-lime text-navy' : 'bg-[#F4F6F1] text-muted'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>

            <div className="flex items-end justify-between gap-8">
              <div className="flex flex-col gap-2">
                <span className="text-base text-muted">{scenario.period} · 투자금 1,000만원</span>
                <div className="flex items-baseline gap-3.5">
                  <span className="text-[44px] font-bold tracking-[-0.035em]">
                    {Math.round(endValue / 10000).toLocaleString('ko-KR')}만원
                  </span>
                  <span className={`text-[19px] font-semibold ${diff >= 0 ? 'text-up' : 'text-down'}`}>
                    {diff >= 0 ? '+' : ''}{Math.round(diff / 10000).toLocaleString('ko-KR')}만원 ({scenario.stratEnd > 0 ? '+' : ''}{scenario.stratEnd}%)
                  </span>
                </div>
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
                  <Tooltip formatter={(v: number) => `${v}%`} labelFormatter={() => ''} />
                  <Legend iconType="plainline" wrapperStyle={{ fontSize: 15, color: '#5C665F' }} />
                  <Line type="monotone" dataKey="KOSPI" stroke="#C3CBC4" strokeWidth={3.5} dot={false} />
                  <Line type="monotone" dataKey="내전략" stroke="#18243A" strokeWidth={5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="flex gap-5 rounded-[20px] bg-[#F8FCEE] px-10 py-9">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-lime text-lg text-navy">✦</div>
              <div className="flex flex-col gap-3">
                <span className="text-[26px] font-bold leading-[38px] tracking-[-0.025em]">{scenario.headline}</span>
                <p className="max-w-[720px] text-lg leading-[30px] text-[#3F4A43]">{scenario.body}</p>
                <div className="flex gap-6 pt-1 text-base text-muted">
                  <span>내 전략 <b className={scenario.stratEnd >= 0 ? 'text-up' : 'text-down'}>{scenario.stratEnd > 0 ? '+' : ''}{scenario.stratEnd}%</b></span>
                  <span>KOSPI <b>{scenario.kospiEnd > 0 ? '+' : ''}{scenario.kospiEnd}%</b></span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-4 gap-8 border-t border-[#F0F2ED] pt-7">
              <Fact label="최대 손실(MDD)" value={strategy.mdd} accent />
              <Fact label="변동성(연)" value={strategy.vol} />
              <Fact label="샤프 지수" value={strategy.sharpe} />
              <Fact label="리밸런싱" value={strategy.rebalance} />
            </div>
          </section>

          <section className="flex items-center justify-between gap-8 rounded-card bg-navy px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-2xl font-bold tracking-[-0.025em] text-white">이 전략으로 시작해볼까요?</span>
              <span className="text-[17px] leading-7 text-[#B9C2BA]">10만원부터 시작할 수 있고, 전략은 언제든 바꿀 수 있어요.</span>
            </div>
            <div className="flex shrink-0 gap-4">
              <button onClick={onOpenBacktest} className="rounded-field bg-white/10 px-9 py-5 text-lg font-bold text-white">
                백테스트 자세히 보기 →
              </button>
              <button onClick={onStart} className="rounded-field bg-lime px-9 py-5 text-lg font-bold text-navy">
                이 전략으로 시작하기 →
              </button>
            </div>
          </section>

          <p className="text-sm leading-[22px] text-subtle">
            ※ 백테스트 결과는 과거 데이터 기반 예시이며 미래 수익을 보장하지 않습니다.
          </p>
        </div>
      </main>
    </div>
  );
}

function Fact({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[15px] text-muted">{label}</span>
      <span className={`text-[22px] font-bold ${accent ? 'text-down' : ''}`}>{value}</span>
    </div>
  );
}
