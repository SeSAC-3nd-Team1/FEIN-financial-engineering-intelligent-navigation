import Header from '../components/Header';
import { STRATEGY_PRODUCT_CARDS } from '../data/strategyProducts';
import type { Screen } from '../types';

/**
 * 2차 디자인 QA — 카드별 subtle color point. 전부 tailwind.config.ts에 이미 등록된 토큰만 쓴다
 * (새 palette 없음). anchor 글자 뒤 매우 연한 tint + CTA hover 색만 바꾸고, 카드 배경/테두리는
 * 손대지 않는다("카드 전체를 강한 색으로 칠하지 않는다" 지침).
 */
const TINT_STYLES: Record<'lime' | 'warm' | 'neutral', { anchorBg: string; anchorText: string; ctaHover: string }> = {
  lime: { anchorBg: 'bg-accent-soft', anchorText: 'text-accent-ink', ctaHover: 'group-hover:text-accent-ink' },
  warm: { anchorBg: 'bg-warn-soft', anchorText: 'text-status-amber-text', ctaHover: 'group-hover:text-status-amber-text' },
  neutral: { anchorBg: 'bg-neutral-100', anchorText: 'text-ink', ctaHover: 'group-hover:text-navy' },
};

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  /** 물림방지 전략 카드 → Coming Soon 상세(실 Model/API 미연결, TODO) */
  onSelectLossAvoidance: () => void;
  /** 방탄 F4 전략집 카드 → F4 4개 전략 선택 화면 */
  onSelectF4: () => void;
  /** 개인 맞춤화 전략 카드 → Preview 화면(투자 시작 CTA 없음) */
  onSelectPersonalizedPreview: () => void;
}

/**
 * 03-0 투자전략 목록(Strategy Main) — Header "투자전략"의 진입점.
 *
 * 물·방·개 전략 체계(물림방지/방탄 F4 전략집/개인 맞춤화) 3개 Product Card를 보여준다. 각 카드
 * 제목의 첫 글자(물/방/개)를 typography로만 강조해 자연스럽게 "물방개" 브랜딩을 발견하게 하되,
 * 화면에 "물방개"라는 이름을 직접 설명하지 않는다. 이 3개는 기존 백엔드 `strategies` 카탈로그
 * (저변동성/가치/모멘텀)와 무관한 프론트엔드 전용 Product Card이며, 각 카드는 아래로 서로 다른
 * 화면(Coming Soon / F4 목록 / Preview)으로 이동한다 — 기존처럼 strategyId를 골라 바로 Strategy
 * Detail로 보내지 않는다(STOP CONDITION: 이번 단계에서 canonical strategy id를 새로 정하지 않음).
 */
export default function StrategyList({
  userName, onNavigate, onSelectLossAvoidance, onSelectF4, onSelectPersonalizedPreview,
}: Props) {
  const handleSelect = (key: (typeof STRATEGY_PRODUCT_CARDS)[number]['key']) => {
    if (key === 'loss-avoidance') onSelectLossAvoidance();
    else if (key === 'f4-collection') onSelectF4();
    else onSelectPersonalizedPreview();
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">투자전략</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
              나에게 맞는 투자전략을<br />살펴보세요
            </h1>
            <p className="max-w-[820px] text-[19px] leading-8 text-muted">
              전략을 골라 자세히 보면, 과거 시장에서 어땠는지와 어떤 방식으로 투자하는지 확인할 수 있어요.
            </p>
          </section>

          <div className="grid grid-cols-3 gap-6">
            {STRATEGY_PRODUCT_CARDS.map((card) => {
              const tint = TINT_STYLES[card.tint];
              return (
                <button
                  key={card.key}
                  onClick={() => handleSelect(card.key)}
                  className="group flex flex-col justify-between gap-10 rounded-card bg-surface p-9 text-left shadow-[0_0_0_1px_#E5E9E3_inset] transition-shadow hover:shadow-[0_0_0_1px_#C9D1C4_inset,0_12px_28px_rgba(24,36,58,0.06)]"
                >
                  <div className="flex flex-col gap-3">
                    {/* Visual Anchor: 기존과 동일하게 font-size 차이(28px/21px)로만 첫 글자를 강조하고,
                       추가로 그 글자 뒤에만 카드별로 매우 연한 tint를 얹는다 — 나머지 글자와 같은 줄,
                       같은 굵기 흐름이라 "물림방지 전략"이 분리된 단어처럼 보이지 않는다. */}
                    <h3 className="tracking-[-0.02em] text-ink">
                      <span className={`mr-0.5 inline-block rounded-md px-1.5 py-0.5 text-[28px] font-extrabold ${tint.anchorBg} ${tint.anchorText}`}>
                        {card.anchor}
                      </span>
                      <span className="text-[21px] font-bold">{card.restOfName}</span>
                    </h3>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-muted">{card.meta}</span>
                      {card.status === 'testing' && (
                        <span className="rounded-full bg-surface-soft px-3 py-1 text-xs font-semibold text-muted">테스트 중</span>
                      )}
                    </div>
                    <p className="text-[16px] leading-[26px] text-muted">{card.description}</p>
                  </div>
                  <span className={`text-[15px] font-semibold text-muted transition-colors ${tint.ctaHover}`}>
                    {card.ctaLabel}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}
