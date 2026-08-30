import { useState } from 'react';
import Header from '../components/Header';
import type { StrategyResponse } from '../lib/backendApi';
import type { Screen } from '../types';

interface Props {
  strategy: StrategyResponse;
  /** STEP 2(확인)에서 "이전"으로 돌아왔을 때 직전에 입력했던 금액을 그대로 보여준다 */
  initialAmount: number;
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
  onContinue: (amount: number) => void;
}

/** 빠른 금액 추가 — 클릭할 때마다 현재 입력값에 더한다(예: 50만원 → +100만원 → 150만원) */
const QUICK_AMOUNTS = [100_000, 500_000, 1_000_000, 5_000_000];
/** 비즈니스 한도가 아니라 순수 JS 숫자 overflow 방지용 자리수 상한(최대 약 9,999억) */
const MAX_DIGITS = 12;
const MAX_AMOUNT = 10 ** MAX_DIGITS - 1;

/**
 * 추가 투자 STEP 1 — 금액 입력. Backend 추가투자 API contract가 아직 없어 최소/최대 투자금,
 * 계좌 잔액, 주문 가능 금액 같은 검증은 하지 않는다(빈 값/0원/숫자 아님/overflow만 방지).
 * target weight/종목별 매수금액 계산은 이 화면에서 하지 않는다 — 확정 정책(추가 금액 × 기존
 * target weight)은 Backend가 처리한다.
 */
export default function FundAddAmount({ strategy, initialAmount, userName, onNavigate, onBack, onContinue }: Props) {
  const [amount, setAmount] = useState(initialAmount);

  const addQuick = (value: number) => {
    setAmount((prev) => Math.min(prev + value, MAX_AMOUNT));
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[720px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <button onClick={onBack} className="self-start text-base font-semibold text-muted">← 나의 포트폴리오</button>
            <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">추가 투자</h1>
          </section>

          {/* 현재 운용 정보 — 실제 계좌의 selected_strategy_id로 해석된 전략(App.tsx의 portfolioStrategy)을
             그대로 받아서 표시한다. 전략명을 하드코딩하지 않는다. */}
          <section className="flex flex-col gap-2 rounded-card bg-surface p-9">
            <span className="text-base text-muted">현재 운용 전략</span>
            <span className="text-[22px] font-bold tracking-[-0.02em] text-ink">{strategy.name}</span>
          </section>

          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <h2 className="text-[26px] font-bold tracking-[-0.025em]">얼마를 추가로 투자할까요?</h2>

            <div className="flex items-center gap-3">
              <input
                value={amount === 0 ? '' : amount.toLocaleString('ko-KR')}
                inputMode="numeric"
                onChange={(e) => {
                  const digits = e.target.value.replace(/[^\d]/g, '').slice(0, MAX_DIGITS);
                  setAmount(digits === '' ? 0 : Math.min(Number(digits), MAX_AMOUNT));
                }}
                placeholder="0"
                className="w-[320px] border-b-2 border-lime bg-transparent px-1 py-3.5 text-[40px] font-bold tracking-[-0.035em] outline-none"
              />
              <span className="text-[28px] font-bold text-muted">원</span>
            </div>

            <div className="flex gap-3">
              {QUICK_AMOUNTS.map((q) => (
                <button
                  key={q}
                  onClick={() => addQuick(q)}
                  className="rounded-full bg-[#F4F6F1] px-6 py-3 text-base font-semibold text-muted"
                >
                  +{(q / 10_000).toLocaleString('ko-KR')}만원
                </button>
              ))}
            </div>

            <div className="flex flex-col gap-1">
              <p className="text-[15px] leading-6 text-ink">추가 금액은 현재 운용 중인 전략에 따라 투자돼요.</p>
              <p className="text-sm leading-5 text-subtle">기존 포지션은 유지하고 추가 금액만 현재 전략의 비중에 따라 투자돼요.</p>
            </div>
          </section>

          <button
            onClick={() => onContinue(amount)}
            disabled={amount <= 0}
            className="rounded-field bg-lime py-5 text-[19px] font-bold text-navy disabled:cursor-default disabled:opacity-60"
          >
            추가 투자 계속하기 →
          </button>
        </div>
      </main>
    </div>
  );
}
