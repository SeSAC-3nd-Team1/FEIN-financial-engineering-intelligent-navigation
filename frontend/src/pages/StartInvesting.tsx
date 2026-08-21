import { useMemo, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';
import Header from '../components/Header';
import { ALL_HOLDINGS } from '../data/holdings';
import { won } from '../lib/validation';
import type { Screen } from '../types';

interface Props {
  userName: string;
  /** RiskResult/StrategyDetail 에서 선택한 전략의 표시 이름 (예: "저변동성 전략") */
  strategyName: string;
  onNavigate: (s: Screen) => void;
  onStart: () => void;
}

const PRESETS = [100_000, 500_000, 1_000_000, 5_000_000];
/** 도넛 색: Deep Navy 계열 + 중립. 선택된 조각만 라임 */
const SHADES = ['#18243A', '#2E4160', '#4A5F80', '#6C819E', '#C3CBC4'];

export default function StartInvesting({ userName, strategyName, onNavigate, onStart }: Props) {
  const [amount, setAmount] = useState(1_000_000);
  const [custom, setCustom] = useState<string | null>(null); // null = 직접 입력 꺼짐
  const [selected, setSelected] = useState(0);
  const [mode, setMode] = useState<'manual' | 'auto'>('manual');

  /** 04는 전략 목표 비중으로 새로 담는다 (target 이 있으면 그 값) */
  const slices = useMemo(() => {
    const top = ALL_HOLDINGS.slice(0, 4).map((h) => ({ name: h.name, pct: h.target ?? h.pct, why: h.why }));
    const restPct = Math.round((100 - top.reduce((a, h) => a + h.pct, 0)) * 10) / 10;
    return [...top, { name: `기타 ${ALL_HOLDINGS.length - 4}개 종목`, pct: restPct, why: '한 종목에 쏠리지 않도록 나머지를 고르게 나눠 담았어요.' }];
  }, []);

  const sel = slices[selected];

  const commitCustom = () => {
    const n = parseInt(custom ?? '', 10);
    if (!n) { setCustom(String(amount)); return; }
    const clamped = Math.min(100_000_000, Math.max(100_000, n));
    setAmount(clamped);
    setCustom(String(clamped));
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">{strategyName}으로 시작하기</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">얼마로 시작해볼까요?</h1>
          </section>

          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <div className="flex gap-3">
              {PRESETS.map((p) => (
                <button
                  key={p}
                  onClick={() => { setAmount(p); setCustom(null); }}
                  className={`rounded-full px-6 py-3.5 text-base font-semibold ${
                    amount === p && custom === null ? 'bg-lime text-navy' : 'bg-[#F4F6F1] text-muted'
                  }`}
                >
                  {(p / 10000).toLocaleString('ko-KR')}만원
                </button>
              ))}
            </div>

            <div className="flex items-end justify-between gap-8">
              <div className="flex flex-col gap-2">
                <span className="text-base text-muted">선택한 투자 금액</span>
                {custom === null ? (
                  <span className="text-[44px] font-bold tracking-[-0.035em]">{won(amount)}</span>
                ) : (
                  <>
                    {/* 직접 입력: 숫자만 받고 blur/Enter 에서 10만~1억으로 보정 */}
                    <div className="flex items-center gap-3">
                      <input
                        value={custom}
                        inputMode="numeric"
                        onChange={(e) => setCustom(e.target.value.replace(/[^\d]/g, '').slice(0, 9))}
                        onBlur={commitCustom}
                        onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
                        placeholder="1000000"
                        className="w-[300px] border-b-2 border-lime bg-transparent px-4 py-3.5 text-[40px] font-bold tracking-[-0.035em] outline-none"
                      />
                      <span className="text-[32px] font-bold text-muted">원</span>
                    </div>
                    <span className="text-[15px] text-subtle">10만원 ~ 1억원 사이로 입력해주세요</span>
                  </>
                )}
              </div>
              <div className="flex flex-col items-end gap-2">
                <button
                  onClick={() => setCustom(custom === null ? String(amount) : null)}
                  className="text-base font-semibold text-navy underline"
                >
                  {custom === null ? '직접 입력' : '금액 선택으로 돌아가기'}
                </button>
                <span className="text-[15px] text-subtle">시작 후에도 언제든 조절할 수 있어요</span>
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-8 rounded-card bg-surface p-12">
            <h2 className="text-[32px] font-bold leading-[46px] tracking-[-0.03em]">
              {(amount / 10000).toLocaleString('ko-KR')}만원을 투자하면 이렇게 나눠 담아요
            </h2>

            <div className="flex items-center gap-14">
              <div className="relative h-[320px] w-[320px] shrink-0">
                <ResponsiveContainer>
                  <PieChart>
                    <Pie
                      data={slices}
                      dataKey="pct"
                      innerRadius="62%"
                      outerRadius="100%"
                      startAngle={90}
                      endAngle={-270}
                      paddingAngle={1.5}
                      stroke="none"
                      onClick={(_, i) => setSelected(i)}
                    >
                      {slices.map((_, i) => (
                        /* 선택된 조각만 라임 — 나머지는 네이비 계열 */
                        <Cell key={i} fill={i === selected ? '#C6F04D' : SHADES[i]} cursor="pointer" />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1">
                  <span className="text-[32px] font-bold tracking-[-0.035em]">
                    {(amount / 10000).toLocaleString('ko-KR')}만원
                  </span>
                  <span className="text-base text-muted">{ALL_HOLDINGS.length}개 종목</span>
                </div>
              </div>

              <div className="flex flex-1 flex-col gap-1">
                {slices.map((h, i) => (
                  <button
                    key={h.name}
                    onClick={() => setSelected(i)}
                    className={`flex items-center gap-4 rounded-2xl px-5 py-4 text-left ${i === selected ? 'bg-[#F8FCEE]' : ''}`}
                  >
                    <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: i === selected ? '#C6F04D' : SHADES[i] }} />
                    <span className="flex-1 text-[18px] font-semibold tracking-[-0.02em]">{h.name}</span>
                    <span className="text-[17px] font-bold">{h.pct.toFixed(1)}%</span>
                    <span className="w-28 text-right text-base text-muted">{won((amount * h.pct) / 100)}</span>
                  </button>
                ))}
                <span className="px-5 pt-2 text-base font-semibold text-navy">나머지 종목 보기 →</span>
              </div>
            </div>

            {/* AI 설명은 선택된 종목에 붙는다 */}
            <div className="flex gap-5 rounded-[20px] bg-[#F8FCEE] px-10 py-9">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-lime text-lg text-navy">✦</div>
              <div className="flex flex-col gap-3">
                <span className="text-[15px] font-semibold text-[#3F5222]">{sel.name} · {sel.pct.toFixed(1)}%</span>
                <span className="text-[22px] font-bold leading-[34px] tracking-[-0.025em]">
                  왜 {sel.name}을 {sel.pct.toFixed(1)}% 담았나요?
                </span>
                <p className="max-w-[720px] text-lg leading-[30px] text-[#3F4A43]">{sel.why}</p>
                <span className="pt-1 text-base font-semibold text-navy">더 자세히 물어보기 →</span>
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <h2 className="text-[26px] font-bold tracking-[-0.025em]">어떻게 운용할까요?</h2>
            <div className="grid grid-cols-2 gap-5">
              <ModeCard
                active={mode === 'manual'}
                onClick={() => setMode('manual')}
                badge="처음이라면 추천"
                title="확인하고 실행"
                flow={['AI가 알려줘요', '내가 확인해요', '실행']}
              />
              <ModeCard
                active={mode === 'auto'}
                onClick={() => setMode('auto')}
                title="자동으로 운용"
                flow={['AI가 판단해요', '자동 실행']}
              />
            </div>
          </section>

          <section className="flex items-center justify-between gap-8 rounded-card bg-navy px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-[17px] text-[#B9C2BA]">{strategyName} · {ALL_HOLDINGS.length}개 종목 · {mode === 'manual' ? '확인하고 실행' : '자동으로 운용'}</span>
              <span className="text-[32px] font-bold tracking-[-0.03em] text-white">{won(amount)}</span>
            </div>
            <button onClick={onStart} className="shrink-0 rounded-field bg-lime px-9 py-5 text-lg font-bold text-navy">
              이대로 시작하기 →
            </button>
          </section>
        </div>
      </main>
    </div>
  );
}

/** 운용 방식 카드 — 긴 설명 대신 mini-flow 로 3초 안에 차이를 보여준다 */
function ModeCard({
  active, onClick, badge, title, flow,
}: { active: boolean; onClick: () => void; badge?: string; title: string; flow: string[] }) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col gap-5 rounded-[20px] p-9 text-left ${
        active ? 'bg-[#F8FCEE] shadow-[0_0_0_2px_#C6F04D_inset]' : 'bg-canvas shadow-[0_0_0_1px_#E5E9E3_inset]'
      }`}
    >
      {badge && <span className="self-start rounded-full bg-lime px-3 py-1.5 text-sm font-bold text-navy">{badge}</span>}
      <span className="text-2xl font-bold tracking-[-0.025em]">{title}</span>
      <div className="flex flex-wrap items-center gap-2">
        {flow.map((step, i) => (
          <span key={step} className="flex items-center gap-2">
            <span className="rounded-[10px] bg-surface px-3.5 py-2.5 text-[15px] font-semibold text-[#3F4A43]">{step}</span>
            {i < flow.length - 1 && <span className="text-[#A6AFA7]">→</span>}
          </span>
        ))}
      </div>
    </button>
  );
}
