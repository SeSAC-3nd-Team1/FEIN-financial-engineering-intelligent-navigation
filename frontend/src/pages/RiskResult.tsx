import { useState } from 'react';
import Header from '../components/Header';
import { STRATEGIES } from '../data/strategies';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  onSelectStrategy: (id: string) => void;
}

/** 02 진단결과 — AI 추천 전략 + 대안 2개. 쉽게/상세 토글로 지표 노출 */
export default function RiskResult({ userName, onNavigate, onSelectStrategy }: Props) {
  const [detail, setDetail] = useState(false);
  const [picked, setPicked] = useState('low');
  const [hero, ...alternatives] = STRATEGIES;

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-16">
          <section className="flex flex-col gap-6">
            <div className="flex items-center justify-between gap-6">
              <span className="text-base font-semibold text-muted">투자성향 진단 · 완료</span>
              <div className="flex items-center gap-2 rounded-full bg-[#F4F6F1] p-1.5">
                <Toggle active={!detail} onClick={() => setDetail(false)}>쉽게 보기</Toggle>
                <Toggle active={detail} onClick={() => setDetail(true)}>상세 지표</Toggle>
              </div>
            </div>
            <h1 className="max-w-[880px] text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
              {userName}님은 안정성과 성장,<br />둘 다 놓치고 싶지 않은 투자자예요.
            </h1>
            <p className="max-w-[820px] text-[19px] leading-8 text-muted">
              큰 손실은 피하고 싶지만 예금처럼 너무 보수적인 투자도 아쉬운 편이에요.
              그래서 시장의 성장에 참여하면서 흔들림을 낮추는 전략부터 보여드릴게요.
            </p>
            <div className="flex items-center gap-5 rounded-card bg-surface px-11 py-9">
              <div className="flex shrink-0 flex-col gap-1.5 border-r border-[#F0F2ED] pr-10">
                <span className="text-[15px] font-bold tracking-[0.06em] text-subtle">BALANCED</span>
                <span className="text-[28px] font-bold tracking-[-0.03em]">중립형</span>
                <span className="text-base text-muted">균형을 찾는 투자</span>
              </div>
              <div className="flex gap-14 pl-10">
                <Fact label="손실 감내" value="보통" />
                <Fact label="투자 기간" value="3년 이상" />
                <Fact label="투자 경험" value="초보" />
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-8">
            <div className="flex flex-col gap-3.5">
              <h2 className="text-[32px] font-bold leading-[46px] tracking-[-0.03em]">가장 잘 맞는 전략부터 볼까요?</h2>
              <p className="text-lg leading-[30px] text-muted">
                AI가 진단 답변과 전략의 과거 위험 특성을 함께 비교했어요. 추천은 참고용이고, 최종 선택은 {userName}님이 해요.
              </p>
            </div>

            <button
              onClick={() => setPicked(hero.id)}
              className={`flex flex-col gap-7 rounded-card bg-surface p-12 text-left ${
                picked === hero.id ? 'shadow-[0_0_0_2px_#C6F04D_inset]' : 'shadow-[0_0_0_1px_#E5E9E3_inset]'
              }`}
            >
              <div className="flex items-start justify-between gap-8">
                <div className="flex flex-col gap-3.5">
                  <span className="self-start rounded-full bg-lime px-3.5 py-2 text-sm font-bold text-navy">✦ AI가 가장 추천해요</span>
                  <span className="text-lg text-muted">{hero.tagline}</span>
                  <span className="text-[38px] font-bold leading-[52px] tracking-[-0.035em]">{hero.name}</span>
                  <span className="text-[22px] font-bold text-[#3F5222]">나와 {hero.match}% 잘 맞아요</span>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <span className="text-[15px] text-muted">과거 5년 기준</span>
                  <span className="text-[40px] font-bold tracking-[-0.035em]">{hero.annual}</span>
                  <span className="text-base text-muted">연평균 수익률 · 위험도 {hero.risk}</span>
                </div>
              </div>

              {detail && (
                <div className="grid grid-cols-4 gap-8 border-t border-[#F0F2ED] pb-1 pt-7">
                  <Fact label="최대 손실(MDD)" value={hero.mdd} accent />
                  <Fact label="변동성(연)" value={hero.vol} />
                  <Fact label="샤프 지수" value={hero.sharpe} />
                  <Fact label="리밸런싱" value={hero.rebalance} />
                </div>
              )}

              <div className="flex gap-5 rounded-[20px] bg-[#F8FCEE] px-9 py-8">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-lime text-lg text-navy">✦</div>
                <div className="flex flex-col gap-3">
                  <span className="text-[22px] font-bold leading-[34px] tracking-[-0.025em]">왜 {hero.name}을 추천했나요?</span>
                  <p className="max-w-[720px] text-lg leading-[30px] text-[#3F4A43]">{hero.why}</p>
                </div>
              </div>

              <span
                onClick={(e) => { e.stopPropagation(); onSelectStrategy(hero.id); }}
                className="self-start rounded-field bg-lime px-9 py-5 text-lg font-bold text-navy"
              >
                이 전략 자세히 보기 →
              </span>
            </button>

            <div className="grid grid-cols-2 gap-5">
              {alternatives.map((s) => (
                <button
                  key={s.id}
                  onClick={() => { setPicked(s.id); onSelectStrategy(s.id); }}
                  className={`flex flex-col gap-4 rounded-card bg-surface p-10 text-left ${
                    picked === s.id ? 'shadow-[0_0_0_2px_#C6F04D_inset]' : 'shadow-[0_0_0_1px_#E5E9E3_inset]'
                  }`}
                >
                  <div className="flex flex-col gap-3">
                    <span className="text-[17px] text-muted">{s.tagline}</span>
                    <span className="text-[28px] font-bold tracking-[-0.03em]">{s.name}</span>
                    <span className="text-[19px] font-bold text-[#3F4A43]">{s.match}% 잘 맞아요</span>
                  </div>
                  <div className="flex items-baseline gap-3">
                    <span className="text-[26px] font-bold tracking-[-0.03em]">{s.annual}</span>
                    <span className="text-base text-muted">연평균 · 위험도 {s.risk}</span>
                  </div>
                  {detail && (
                    <span className="text-base text-muted">MDD {s.mdd} · 변동성 {s.vol} · 샤프 {s.sharpe}</span>
                  )}
                  <span className="text-[17px] font-semibold text-navy">자세히 보기 →</span>
                </button>
              ))}
            </div>
          </section>

          <p className="text-sm leading-[22px] text-subtle">
            ※ 백테스트 수익률은 과거 데이터 기반 예시이며 미래 수익을 보장하지 않습니다.
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
      className={`rounded-full px-6 py-3 text-base font-semibold ${
        active ? 'bg-surface text-ink shadow-[0_2px_8px_rgba(24,36,58,0.08)]' : 'text-muted'
      }`}
    >
      {children}
    </button>
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
