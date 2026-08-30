import Header from '../components/Header';
import { STRATEGY_PRODUCT_CARDS } from '../data/strategyProducts';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
}

const EXAMPLE_INPUTS = [
  '내가 중요하게 보는 투자 기준',
  '선호하는 종목 특성',
  '매수·매도 판단 스타일',
];

/**
 * 개인 맞춤화 전략 Preview — 실제 투자 기능이 아니라 정보구조 미리보기다. 실제 데이터/수익률/
 * 추천 결과를 임의로 만들지 않고, 어떤 정보를 바탕으로 개인화가 이뤄지는지 example shell만 보여준다.
 * 모델링 담당자의 실제 example은 추후 이 shell 안에 채워 넣을 수 있다(TODO).
 * "이 전략으로 시작하기" 같은 투자 시작 CTA는 의도적으로 만들지 않는다.
 */
export default function StrategyPersonalizedPreview({ userName, onNavigate, onBack }: Props) {
  const card = STRATEGY_PRODUCT_CARDS.find((c) => c.key === 'personalized');
  if (!card) return null;

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <button
              onClick={onBack}
              className="self-start text-[15px] font-semibold text-muted transition-colors hover:text-navy"
            >
              ← 투자전략 목록
            </button>
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold text-muted">{card.meta}</span>
              <span className="rounded-full bg-surface-soft px-3 py-1 text-xs font-semibold text-muted">테스트 중</span>
            </div>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">{card.name}</h1>
            <p className="max-w-[820px] text-[19px] leading-8 text-muted">
              나의 투자 기준을 학습해 나를 대신해 투자하는 전략을 준비하고 있어요.
            </p>
          </section>

          <section className="flex flex-col gap-8 rounded-card bg-surface p-12">
            <span className="text-[15px] font-bold text-muted">이런 방식으로 활용할 수 있어요</span>

            <div className="flex flex-col gap-3">
              {EXAMPLE_INPUTS.map((label) => (
                <div key={label} className="flex items-center rounded-[16px] bg-canvas px-7 py-5">
                  <span className="text-[17px] font-semibold text-ink">{label}</span>
                </div>
              ))}
            </div>

            <span className="self-center text-2xl text-subtle">↓</span>

            <div className="flex items-center justify-center rounded-[16px] bg-accent-soft px-7 py-6">
              <span className="text-[19px] font-bold text-accent-ink">나의 투자 스타일을 반영한 전략</span>
            </div>

            <p className="text-sm leading-[22px] text-subtle">
              ※ 실제 예시는 모델이 연결된 뒤 제공될 예정이에요. 위 내용은 어떤 정보를 활용하는지 보여주는 정보구조 예시입니다.
            </p>
          </section>
        </div>
      </main>
    </div>
  );
}
