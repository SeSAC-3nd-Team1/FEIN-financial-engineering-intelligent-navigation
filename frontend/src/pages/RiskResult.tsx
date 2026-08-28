import { useRef, useState } from 'react';
import { Info } from 'lucide-react';
import Header from '../components/Header';
import { useAuthStore } from '../store/authStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
}

/**
 * 02 결과 — 전략 추천 모델이 아직 없어(#추천 모델 미구현) "투자성향 → AI 추천"이 아니라
 * "투자성향 → 나의 성향 이해 → 전략 비교 → 직접 선택"으로 다음 단계를 안내한다. 투자성향 진단
 * 자체(실 API 결과인 investorType/investorDescription)는 그대로 유지하고, 그 아래에 있던
 * AI 추천 카드/백테스트 비교/error-retry UI를 전부 제거했다 — 존재하지 않는 추천 결과를 흉내
 * 내지 않기 위해서다. CTA는 새 화면을 만들지 않고 기존 StrategyList(strategy-list)로 보낸다.
 */
export default function RiskResult({ userName, onNavigate }: Props) {
  const investorType = useAuthStore((s) => s.investorType);
  const investorDescription = useAuthStore((s) => s.investorDescription);

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <section className="flex flex-col gap-5 pb-6">
            <span className="text-base font-semibold text-muted">투자자 정보 확인 · 완료</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">투자성향을 확인했어요</h1>
            {investorType && investorDescription ? (
              <div className="flex items-center gap-2.5">
                <span className="rounded-full bg-lime px-5 py-2.5 text-[22px] font-bold text-navy">{investorType}이에요</span>
                <InvestorTypeInfo type={investorType} description={investorDescription} />
              </div>
            ) : (
              <p className="text-lg text-muted">저장된 투자성향 정보가 없어요.</p>
            )}
          </section>

          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <p className="text-lg leading-[30px] text-muted">
              투자성향은 전략을 선택할 때 참고할 수 있는 정보예요.<br />
              각 전략의 특징과 투자 방식을 비교해 나에게 맞는 전략을 직접 선택해보세요.
            </p>
            <button
              onClick={() => onNavigate('strategy-list')}
              className="self-start rounded-field bg-lime px-9 py-5 text-lg font-bold text-navy"
            >
              투자 전략 살펴보기 →
            </button>
          </section>
        </div>
      </main>
    </div>
  );
}

/** 투자유형 설명은 hover·tap·키보드 focus 모두에서 확인할 수 있다. */
function InvestorTypeInfo({ type, description }: { type: string; description: string }) {
  const [hoverCapable] = useState(() => typeof window !== 'undefined' && window.matchMedia?.('(hover: hover) and (pointer: fine)').matches);
  const [open, setOpen] = useState(false);
  const pointerActivated = useRef(false);
  const markPointer = () => { pointerActivated.current = true; };

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label={`${type} 설명 보기`}
        aria-expanded={open}
        onMouseDown={markPointer}
        onTouchStart={markPointer}
        onMouseEnter={() => hoverCapable && setOpen(true)}
        onMouseLeave={() => hoverCapable && setOpen(false)}
        onFocus={() => {
          if (pointerActivated.current) { pointerActivated.current = false; return; }
          setOpen(true);
        }}
        onBlur={() => setOpen(false)}
        onClick={() => {
          if (hoverCapable) { setOpen(true); return; }
          setOpen((value) => !value);
        }}
        className="flex h-8 w-8 items-center justify-center rounded-full text-subtle hover:text-navy"
      >
        <Info size={22} />
      </button>
      {open && (
        <div role="tooltip" className="absolute left-0 top-full z-10 mt-2 w-[280px] rounded-[14px] bg-navy px-5 py-4 text-[15px] leading-6 text-white shadow-[0_8px_24px_rgba(24,36,58,0.25)]">
          {description}
        </div>
      )}
    </span>
  );
}
