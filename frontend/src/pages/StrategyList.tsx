import { useRef, useState } from 'react';
import { Clock, Info } from 'lucide-react';
import Header from '../components/Header';
import { STRATEGY_PRODUCT_CARDS } from '../data/strategyProducts';
import { useAuthStore } from '../store/authStore';
import type { Screen } from '../types';

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
  const investorType = useAuthStore((s) => s.investorType);
  const investorDescription = useAuthStore((s) => s.investorDescription);

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
              투자전략을 살펴보세요
            </h1>
            <p className="max-w-[820px] text-[19px] leading-8 text-muted">
              전략을 골라 자세히 보면, 과거 시장에서 어땠는지와 어떤 방식으로 투자하는지 확인할 수 있어요.
            </p>
          </section>

                    {investorType && (
            <section className="flex flex-col gap-5 pb-6">
              <span className="text-base font-semibold text-muted">투자자 정보 확인 · 완료</span>
              <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
                투자성향을 확인했어요
              </h1>
              <div className="flex items-center gap-2.5">
                <span className="rounded-full bg-lime px-5 py-2.5 text-[22px] font-bold text-navy">{investorType}이에요</span>
                <InvestorTypeInfo type={investorType} description={investorDescription ?? ''} />
              </div>
            </section>
          )}

          <div className="grid grid-cols-3 gap-6">
            {STRATEGY_PRODUCT_CARDS.map((card) => (
              <button
                key={card.key}
                onClick={() => handleSelect(card.key)}
                className="group flex flex-col justify-between gap-10 rounded-card bg-surface p-9 text-left shadow-[0_0_0_1px_#E5E9E3_inset] transition-shadow hover:shadow-[0_0_0_1px_#C9D1C4_inset,0_12px_28px_rgba(24,36,58,0.06)]"
              >
                <div className="flex flex-col gap-3">
                  {/* Visual Anchor: 배경/색 없이 font-size(24px/21px)·font-weight 차이만으로 첫 글자를
                     살짝 강조한다 — 같은 줄, 같은 ink 색으로 이어 써서 "물림방지 전략"이 분리된
                     단어처럼 보이지 않는다. 3장 모두 동일한 처리라 카드별로 다른 색이 생기지 않는다. */}
                  <h3 className="tracking-[-0.02em] text-ink">
                    <span className="text-[24px] font-extrabold">{card.anchor}</span>
                    <span className="text-[21px] font-bold">{card.restOfName}</span>
                  </h3>
                  {/* Secondary info: 전부 compact pill이되 역할별로 hierarchy를 나눈다 — metadata
                     3개(물림방지/F4/개인맞춤)는 전부 동일한 neutral로 통일한다(lime은 "이용 가능"
                     같은 active 신호와 겹치지 않도록 CTA 화살표에만 남겨둔다). "테스트 중"은
                     metadata와 구분되는 status라 아이콘 + 한 단계 더 진한 neutral을 써서 한눈에
                     상태로 읽히게 한다. 카드 배경이 흰색(surface)이라 배경색 차이만으로는 pill
                     윤곽이 잘 안 보여, 기존 카드 테두리와 같은 hairline border(line 토큰)를 모든
                     배지에 둘러 윤곽을 확실히 잡아준다. */}
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-neutral-100 px-3 py-1 text-xs font-semibold text-muted shadow-[0_0_0_1px_#E5E9E3_inset]">
                      {card.meta}
                    </span>
                    {/* 난이도 태그: 투자 위험등급이 아니라 "이해/접근 난이도" 안내용 정적 메타데이터라
                       위 meta pill과 동일한 neutral 스타일을 그대로 재사용한다 — 별도 강조를 주면
                       마치 투자성향 기반 추천처럼 보일 수 있어 의도적으로 시각적 위계를 두지 않았다. */}
                    <span className="rounded-full bg-neutral-100 px-3 py-1 text-xs font-semibold text-muted shadow-[0_0_0_1px_#E5E9E3_inset]">
                      {card.difficulty}
                    </span>
                    {card.status === 'testing' && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-neutral-150 px-3 py-1 text-xs font-bold text-ink-soft shadow-[0_0_0_1px_#E5E9E3_inset]">
                        <Clock size={11} />
                        테스트 중
                      </span>
                    )}
                  </div>
                  <p className="text-[16px] leading-[26px] text-muted">{card.description}</p>
                </div>
                {/* CTA: 텍스트 라벨은 그대로, 화살표만 FE!N lime accent(선택/CTA 전용 색)를 쓰는
                   작은 원형으로 분리 — 카드 전체를 lime으로 칠하지 않고 발견성만 살짝 높인다. */}
                <div className="flex items-center justify-between">
                  <span className="text-[15px] font-semibold text-muted">{card.ctaLabel}</span>
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-lime text-navy transition-transform group-hover:translate-x-0.5">
                    →
                  </span>
                </div>
              </button>
            ))}
          </div>
                </div>
      </main>
    </div>
  );
}

/** 투자유형 설명은 hover·tap·키보드 focus 모두에서 확인할 수 있다. */
function InvestorTypeInfo({ type, description }: { type: string; description: string }) {
  const [hoverCapable] = useState(
    () => typeof window !== 'undefined' && window.matchMedia?.('(hover: hover) and (pointer: fine)').matches,
  );
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
        <div
          role="tooltip"
          className="absolute left-0 top-full z-10 mt-2 w-[280px] rounded-[14px] bg-navy px-5 py-4 text-[15px] leading-6 text-white shadow-[0_8px_24px_rgba(24,36,58,0.25)]"
        >
          {description}
        </div>
      )}
    </span>
  );
}