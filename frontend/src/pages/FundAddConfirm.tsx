import Header from '../components/Header';
import { won } from '../lib/validation';
import type { StrategyResponse } from '../lib/backendApi';
import type { Screen } from '../types';

interface Props {
  strategy: StrategyResponse;
  /** STEP 1에서 넘어온 금액 — 여기서 새로 계산하거나 만들지 않는다 */
  amount: number;
  userName: string;
  onNavigate: (s: Screen) => void;
  /** STEP 1(금액 입력)로 돌아간다 — 입력했던 금액은 App.tsx가 그대로 들고 있어 유지된다 */
  onBack: () => void;
  /** "추가 투자하기" — 실제 매수/Backend 연동 전이라 완료 처리 없이 준비 중 화면(STEP 3)으로만 이동한다 */
  onConfirm: () => void;
}

/**
 * 추가 투자 STEP 2 — 내용 확인. "추가 후 총 투자원금"은 표시하지 않는다: canonical 값
 * (portfolio.total_purchase_amount)에 이 화면의 입력 금액을 더하는 계산이 기존 계좌/mock 분기와
 * 완전히 맞아떨어지는지 확신할 수 없어, 가짜 값을 보여주는 대신 생략했다(STOP 대신 생략 우선).
 */
export default function FundAddConfirm({ strategy, amount, userName, onNavigate, onBack, onConfirm }: Props) {
  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[720px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <button onClick={onBack} className="self-start text-base font-semibold text-muted">← 이전</button>
            <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">추가 투자 내용을 확인해주세요</h1>
          </section>

          <section className="flex flex-col gap-5 rounded-card bg-surface p-9">
            <div className="flex items-center justify-between">
              <span className="text-base text-muted">현재 운용 전략</span>
              <span className="text-lg font-bold text-ink">{strategy.name}</span>
            </div>
            <div className="h-px bg-line" />
            <div className="flex items-center justify-between">
              <span className="text-base text-muted">추가 투자 금액</span>
              <span className="text-[22px] font-bold tracking-[-0.02em] text-ink">{won(amount)}</span>
            </div>
            <div className="h-px bg-line" />
            <div className="flex items-center justify-between">
              <span className="text-base text-muted">투자 방식</span>
              <span className="text-lg font-semibold text-ink">현재 전략에 추가 투자</span>
            </div>
          </section>

          <p className="text-[15px] leading-6 text-muted">
            기존 보유 종목은 그대로 유지되고, 추가 금액만 현재 전략의 비중에 따라 투자돼요.
          </p>

          <div className="flex gap-3">
            <button
              onClick={onBack}
              className="flex-1 rounded-field bg-[#F4F6F1] py-4 text-base font-semibold text-[#3F4A43]"
            >
              이전
            </button>
            <button
              onClick={onConfirm}
              className="flex-1 rounded-field bg-lime py-4 text-base font-bold text-navy"
            >
              추가 투자하기
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
