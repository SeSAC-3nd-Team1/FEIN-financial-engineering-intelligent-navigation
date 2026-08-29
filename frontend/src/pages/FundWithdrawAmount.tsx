import { useState } from 'react';
import Header from '../components/Header';
import { won } from '../lib/validation';
import type { StrategyResponse } from '../lib/backendApi';
import { useTradingData } from '../hooks/useTradingData';
import { useTradingStore } from '../store/tradingStore';
import type { Screen } from '../types';

interface Props {
  strategy: StrategyResponse;
  /** STEP 2에서 "이전"으로 돌아왔을 때 직전 입력 금액을 그대로 보여준다 */
  initialAmount: number;
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
  onContinue: (amount: number) => void;
}

/** 추가투자(FundAddAmount)와 동일한 가산형 quick amount — 클릭할 때마다 현재 입력값에 더한다 */
const QUICK_AMOUNTS = [100_000, 500_000, 1_000_000];
/** 비즈니스 한도가 아니라 순수 JS 숫자 overflow 방지용 자리수 상한 */
const MAX_DIGITS = 12;
const MAX_AMOUNT = 10 ** MAX_DIGITS - 1;

/**
 * 투자금 출금 STEP 1 — 금액 입력. 추가투자(FundAddAmount)와 동일한 디자인 언어를 재사용하되,
 * 출금 고유 정책을 반영한다:
 * - "출금 가능 금액"은 Backend에 canonical field(withdrawable_amount 등)가 없어(lib/backendApi.ts
 *   확인 결과 전무) 정직한 안내 문구로 대체하고 숫자를 임의로 계산하지 않는다.
 * - "전액" quick amount는 출금 가능 금액이 없으면 자동 입력 기능을 만들 수 없어 disabled로 둔다.
 * - 최소/최대 출금액, 계좌 잔액, 매도 가능 수량 등 Backend 정책 검증은 하지 않는다(TODO).
 */
export default function FundWithdrawAmount({ strategy, initialAmount, userName, onNavigate, onBack, onContinue }: Props) {
  const [amount, setAmount] = useState(initialAmount);

      // 포트폴리오 조회 결과가 없으면 임의의 평가금액 대신 0원을 표시한다.
  useTradingData();
  const portfolio = useTradingStore((s) => s.portfolio);
  const currentValuation = Number(portfolio?.total_assets ?? 0);

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
            <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">투자금 출금</h1>
          </section>

          <section className="flex flex-col gap-2 rounded-card bg-surface p-9">
            <span className="text-base text-muted">현재 운용 전략</span>
            <span className="text-[22px] font-bold tracking-[-0.02em] text-ink">{strategy.name}</span>
            <div className="mt-2 h-px bg-line" />
            <div className="mt-2 flex items-center justify-between">
              <span className="text-base text-muted">현재 평가금액</span>
              <span className="text-lg font-semibold text-ink">{won(currentValuation)}</span>
            </div>
          </section>

          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <h2 className="text-[26px] font-bold tracking-[-0.025em]">얼마를 출금할까요?</h2>

            {/* 출금 가능 금액 — Backend에 canonical field가 없어 숫자 대신 정직한 안내만 표시 */}
            <p className="text-sm text-subtle">출금 가능 금액은 출금 연결 후 확인할 수 있어요.</p>

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
              {/* 전액 — 출금 가능 금액이 Backend에서 확정되기 전까지는 자동 입력 기능을 만들지 않고 비활성으로만 둔다 */}
              <button
                disabled
                className="rounded-full bg-disabled-bg px-6 py-3 text-base font-semibold text-disabled-text cursor-default"
              >
                전액
              </button>
            </div>

            <div className="flex flex-col gap-1">
              <p className="text-[15px] leading-6 text-ink">출금을 위해 보유 종목 일부가 매도될 수 있어요.</p>
              <p className="text-sm leading-5 text-subtle">출금 후에도 현재 운용 중인 전략은 그대로 유지돼요.</p>
            </div>
          </section>

          <button
            onClick={() => onContinue(amount)}
            disabled={amount <= 0}
            className="rounded-field bg-lime py-5 text-[19px] font-bold text-navy disabled:cursor-default disabled:opacity-60"
          >
            출금 계속하기 →
          </button>
        </div>
      </main>
    </div>
  );
}
