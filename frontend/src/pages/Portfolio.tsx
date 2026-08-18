import { useMemo, useState } from 'react';
import { X } from 'lucide-react';
import Header from '../components/Header';
import { ALL_HOLDINGS, HOLD_TOTAL } from '../data/holdings';
import { won } from '../lib/validation';
import type { Screen } from '../types';

interface Props {
  userName: string;
  /** 모달에서 선택·표시되는 현재 전략 */
  strategy: Strategy;
  onStrategyChange: (s: Strategy) => void;
  onNavigate: (s: Screen) => void;
  onSelectStock: (index: number) => void;
  /** 모달의 "다시 진단하기" — 투자성향 진단으로 되돌린다 */
  onRediagnose: () => void;
  onBack: () => void;
}

export const STRATEGY_NAMES = ['저변동성', '가치', '모멘텀'] as const;
export type Strategy = (typeof STRATEGY_NAMES)[number];

export default function Portfolio({
  userName, strategy, onStrategyChange, onNavigate, onSelectStock, onRediagnose, onBack,
}: Props) {
  // 전략 변경 모달 상태
  const [isModalOpen, setModalOpen] = useState(false);
  const selectedStrategy = strategy;
  const setSelectedStrategy = onStrategyChange;

  /** 오늘 손익 = 평가금액 × 등락률. 요약과 종목 행이 같은 계산을 쓴다 */
  const gains = useMemo(
    () => ALL_HOLDINGS.map((h) => ({ ...h, gain: (HOLD_TOTAL * h.pct) / 100 * (h.chg / 100) })),
    []
  );
  const todayTotal = gains.reduce((a, g) => a + g.gain, 0);

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
              <span className="text-[40px] font-bold tracking-[-0.035em]">{won(HOLD_TOTAL)}</span>
              <span className="text-xl font-bold text-up">
                오늘 {todayTotal >= 0 ? '+' : ''}{Math.round(todayTotal).toLocaleString('ko-KR')}원
              </span>
            </div>
          </section>

          {/* 현재 전략 + 변경 트리거 — Primary 로 강조하지 않는다 */}
          <section className="flex items-center justify-between gap-8 rounded-card bg-surface px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-[15px] text-muted">현재 전략</span>
              <span className="text-2xl font-bold tracking-[-0.025em]">{selectedStrategy} 전략</span>
              <span className="text-base text-muted">나와 92% 잘 맞아요</span>
            </div>
            <button
              onClick={() => setModalOpen(true)}
              className="shrink-0 rounded-field bg-[#F4F6F1] px-7 py-4 text-[17px] font-semibold text-[#3F4A43]"
            >
              전략 변경하기
            </button>
          </section>

          <section className="flex flex-col gap-5 rounded-card bg-surface p-12">
            <div className="flex items-baseline justify-between">
              <h2 className="text-[26px] font-bold tracking-[-0.025em]">전체 20개 종목</h2>
              <span className="text-[15px] text-subtle">종목을 누르면 상세 정보를 볼 수 있어요</span>
            </div>
            <div className="flex flex-col">
              {gains.map((h, i) => (
                <button
                  key={h.name}
                  onClick={() => onSelectStock(i)}
                  className="flex items-center gap-5 border-b border-line py-4 text-left last:border-0 hover:bg-canvas"
                >
                  <span className="w-7 shrink-0 text-[15px] text-subtle">{i + 1}</span>
                  <div className="flex flex-1 flex-col gap-1">
                    <span className="text-[18px] font-semibold tracking-[-0.02em]">{h.name}</span>
                    <span className="text-[14px] text-subtle">{h.sector}</span>
                  </div>
                  <span className="w-24 text-right text-[17px] font-bold">{h.pct.toFixed(1)}%</span>
                  <span className="w-32 text-right text-[16px] text-muted">{won((HOLD_TOTAL * h.pct) / 100)}</span>
                  <span className={`w-20 text-right text-[16px] font-semibold ${h.chg > 0 ? 'text-up' : h.chg < 0 ? 'text-down' : 'text-subtle'}`}>
                    {h.chg > 0 ? '+' : ''}{h.chg.toFixed(1)}%
                  </span>
                </button>
              ))}
            </div>
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
              {STRATEGY_NAMES.map((s) => {
                const active = s === selectedStrategy;
                return (
                  <button
                    key={s}
                    onClick={() => setSelectedStrategy(s)}
                    className={`flex items-center justify-between rounded-[20px] px-8 py-7 text-left ${
                      active ? 'bg-[#F8FCEE] shadow-[0_0_0_2px_#C6F04D_inset]' : 'bg-canvas shadow-[0_0_0_1px_#E5E9E3_inset]'
                    }`}
                  >
                    <span className="text-[22px] font-bold tracking-[-0.02em]">{s} 전략</span>
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
