import Header from '../components/Header';
import TermTooltip from '../components/TermTooltip';
import { F4_COLLECTION_INTRO, F4_SUB_STRATEGIES } from '../data/strategyProducts';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
  /** 실제 canonical momentum 전략 상세로 이동한다. */
  onSelectMomentum: () => void;
  /** 기존 이벤트 드리븐 Coming Soon 상세로 이동한다. */
  onSelectEventDriven: () => void;
}

/**
 * 방탄 F4 전략집 — Strategy Main "방탄 F4 전략집" 카드에서 진입. Strategy Main/Detail과 같은
 * 레이아웃(Header, w-[1040px] container, 카드 스타일)을 재사용한다. 4개 중 모멘텀만
 * "이용 가능" 배지 + CTA를 갖고, 나머지 3개는 muted "테스트 중" 배지 + TermTooltip 안내 +
 * 비활성 버튼으로 처리한다(새 modal/복잡한 interaction 없음).
 */
export default function StrategyF4List({
  userName, onNavigate, onBack, onSelectMomentum, onSelectEventDriven,
}: Props) {
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
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">{F4_COLLECTION_INTRO.name}</h1>
            <p className="max-w-[820px] text-[19px] leading-8 text-muted">{F4_COLLECTION_INTRO.description}</p>
          </section>

          <div className="grid grid-cols-2 gap-6">
            {F4_SUB_STRATEGIES.map((s) => {
              const available = s.status === 'available';
              return (
                <div
                  key={s.id}
                  className={`flex flex-col justify-between gap-8 rounded-card bg-surface p-9 ${
                    // 상태 hierarchy: "이용 가능" 카드만 테두리를 살짝 진하고 두껍게(status-green 톤)
                    // 해서 눈에 먼저 들어오게 한다. 배경 tint/gradient 등 다른 효과는 더 얹지 않는다
                    // ("추천 카드"처럼 보이지 않도록 1~2개 효과로 제한).
                    available ? 'shadow-[0_0_0_1.5px_#2E9B65_inset]' : 'shadow-[0_0_0_1px_#E5E9E3_inset]'
                  }`}
                >
                  <div className="flex flex-col gap-3">
                    <div className="flex items-start justify-between gap-3">
                      <span className="text-[21px] font-bold tracking-[-0.02em] text-ink">{s.name}</span>
                      {available ? (
                        <span className="shrink-0 rounded-full bg-status-green-bg px-3 py-1.5 text-xs font-bold text-status-green-text">
                          ● 이용 가능
                        </span>
                      ) : (
                        <div className="flex shrink-0 items-center gap-1.5">
                          <span className="rounded-full bg-surface-soft px-3 py-1 text-xs font-semibold text-ink-soft">테스트 중</span>
                          <TermTooltip label="테스트 중" description="현재 모델을 검증하고 있어요. 준비되는 대로 만나볼 수 있어요." />
                        </div>
                      )}
                    </div>
                    <p className="text-[16px] leading-[26px] text-muted">{s.description}</p>
                  </div>
                  {available ? (
                    <button
                      onClick={() => {
                        if (s.id === 'f4-momentum') onSelectMomentum();
                        if (s.id === 'f4-event-driven') onSelectEventDriven();
                      }}
                      className="group self-start text-[15px] font-bold text-status-green-text transition-colors hover:text-navy"
                    >
                      자세히 보기 →
                    </button>
                  ) : (
                    <button
                      disabled
                      className="self-start rounded-field bg-disabled-bg px-6 py-3 text-[15px] font-bold text-disabled-text cursor-default"
                    >
                      준비 중
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}
