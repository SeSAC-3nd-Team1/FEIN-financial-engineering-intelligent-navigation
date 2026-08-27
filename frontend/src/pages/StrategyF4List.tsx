import Header from '../components/Header';
import TermTooltip from '../components/TermTooltip';
import { F4_COLLECTION_INTRO, F4_SUB_STRATEGIES } from '../data/strategyProducts';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
  /** status가 'available'인 전략만 실제 상세(Coming Soon)로 이동한다 — 현재는 모멘텀 전략 하나뿐이고,
   * 나머지 3개(가치주/통계적 차익거래/이벤트 드리븐)는 테스트 중 상태만 안내한다. */
  onSelectAvailableStrategy: () => void;
}

/**
 * 방탄 F4 전략집 — Strategy Main "방탄 F4 전략집" 카드에서 진입. Strategy Main/Detail과 같은
 * 레이아웃(Header, w-[1040px] container, 카드 스타일)을 재사용한다. F4_SUB_STRATEGIES에서
 * status가 'available'인 전략(현재 모멘텀) 하나만 "이용 가능" 배지 + CTA를 갖고, 나머지는 muted
 * "테스트 중" 배지 + TermTooltip 안내 + 비활성 버튼으로 처리한다(새 modal/복잡한 interaction 없음).
 * MVP 대상이 바뀌어도(예: 모멘텀 → 다른 전략) data 배열의 status만 바꾸면 되도록 status 기반으로
 * 렌더링한다 — 특정 전략 id를 하드코딩해 분기하지 않는다.
 *
 * 3차 디자인 QA: "이용 가능" 강조는 FE!N lime accent 하나로 통일한다(카드 테두리 색 구분은 걷어냄) —
 * badge를 lime으로, CTA를 Strategy Main과 동일한 lime circular arrow로 맞춰 색을 여러 개
 * 쓰지 않으면서도 "지금 쓸 수 있는 전략"이라는 신호가 명확하게 남도록 했다.
 */
export default function StrategyF4List({ userName, onNavigate, onBack, onSelectAvailableStrategy }: Props) {
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
                  className="flex flex-col justify-between gap-8 rounded-card bg-surface p-9 shadow-[0_0_0_1px_#E5E9E3_inset]"
                >
                  <div className="flex flex-col gap-3">
                    <div className="flex items-start justify-between gap-3">
                      <span className="text-[21px] font-bold tracking-[-0.02em] text-ink">{s.name}</span>
                      {available ? (
                        <span className="shrink-0 rounded-full bg-lime px-3 py-1.5 text-xs font-bold text-navy">
                          이용 가능
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
                    <button onClick={onSelectAvailableStrategy} className="group flex items-center justify-between gap-4">
                      <span className="text-[15px] font-semibold text-muted">자세히 보기</span>
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-lime text-navy transition-transform group-hover:translate-x-0.5">
                        →
                      </span>
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
