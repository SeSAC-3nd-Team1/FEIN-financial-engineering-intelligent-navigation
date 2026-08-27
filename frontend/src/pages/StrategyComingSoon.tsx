import { Clock } from 'lucide-react';
import Header from '../components/Header';
import { COMING_SOON_COPY } from '../data/strategyProducts';
import type { Screen } from '../types';

interface Props {
  strategyKey: keyof typeof COMING_SOON_COPY;
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
}

/**
 * 물림방지 / 이벤트 드리븐 전략 상세 — 이번 UI/IA 1차 개편 STOP CONDITION(새 canonical strategy id
 * 결정 금지, 새 Backtest response 정의 금지, 기존 mock 데이터를 새 전략인 것처럼 위장 금지)에 따라
 * 실제 Model/API를 연결하지 않는다.
 *
 * 대신 기존 StrategyDetail의 정보 hierarchy(제목/설명 → 기간 선택 → 백테스트 결과 → AI 설명 →
 * 투자 시작 CTA → disclaimer)와 같은 위치에 "준비 중" placeholder를 배치해, 실제 Model/Backend
 * contract가 확정되면 이 화면을 실제 StrategyDetail(strategyId 기반)로 교체할 수 있게만 해둔다.
 * 임의의 수치·차트·AI 설명은 만들지 않는다(TODO: Mock/실제 Model contract 확정 후 실 연동).
 */
export default function StrategyComingSoon({ strategyKey, userName, onNavigate, onBack }: Props) {
  const copy = COMING_SOON_COPY[strategyKey];

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
              {copy.backLabel}
            </button>
            <span className="text-base font-semibold text-muted">{copy.meta}</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">{copy.name}</h1>
            <p className="max-w-[820px] text-[19px] leading-8 text-muted">{copy.description}</p>
          </section>

          {/* 기존 백테스트 chart/지표 영역과 같은 위치 — 실제 데이터 대신 준비 중 안내만 표시 */}
          <section className="flex flex-col items-center gap-5 rounded-card bg-surface px-10 py-20 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-[18px] bg-surface-soft text-muted">
              <Clock size={26} />
            </div>
            <h2 className="text-2xl font-bold tracking-[-0.025em]">백테스트를 준비하고 있어요</h2>
            <p className="max-w-[520px] text-[17px] leading-7 text-muted">
              실제 모델이 연결되면 기간별 성과와 지표를 여기서 확인할 수 있어요.
            </p>
          </section>

          {/* 기존 AI 설명 카드와 같은 위치/스타일 — 캐릭터는 기존 것을 그대로 재사용 */}
          <section className="flex gap-6 rounded-[20px] bg-accent-soft px-10 py-9">
            <img src="/character-thinking.png" alt="물방개" className="h-20 w-20 shrink-0 object-contain" />
            <div className="flex flex-1 flex-col gap-2">
              <span className="text-[22px] font-bold leading-[34px] tracking-[-0.025em]">
                모델이 준비되면 물방개가 결과를 설명해드릴게요
              </span>
              <p className="max-w-[760px] text-lg leading-[30px] text-ink-soft">
                지금은 이 전략의 정보구조만 먼저 볼 수 있어요.
              </p>
            </div>
          </section>

          {/* 기존 투자 시작 CTA와 같은 위치 — 실제 CTA는 아직 연결하지 않는다 */}
          <section className="flex items-center justify-between gap-8 rounded-card bg-navy px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-2xl font-bold tracking-[-0.025em] text-white">투자 시작은 아직 준비 중이에요</span>
              <span className="text-[17px] leading-7 text-neutral-muted">모델이 연결되면 이 전략으로 투자를 시작할 수 있어요.</span>
            </div>
            <span className="shrink-0 rounded-full bg-white/10 px-7 py-4 text-base font-bold text-white">
              준비 중
            </span>
          </section>

          <p className="text-sm leading-[22px] text-subtle">
            ※ 이 전략은 아직 실제 모델과 연결되지 않았어요. 위 화면은 정보구조 확인을 위한 준비 화면입니다.
          </p>
        </div>
      </main>
    </div>
  );
}
