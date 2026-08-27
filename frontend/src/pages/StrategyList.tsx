import Header from '../components/Header';
import type { StrategyResponse } from '../lib/backendApi';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  strategies: StrategyResponse[];
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  /** Strategy Card 선택 → 기존 Strategy Detail(strategy 화면)로 이동 */
  onSelectStrategy: (id: string) => void;
}

/**
 * 03-0 투자전략 목록 — Header "투자전략"의 진입점. 카드는 이름/한 줄 설명만 보여주는
 * Progressive Disclosure 1단계이고, 지표·백테스트 등은 기존 Strategy Detail(상세)에서 보여준다.
 * 전략 모델이 아직 확정 전이라 카드에는 최소 정보만 노출한다.
 */
export default function StrategyList({
  userName, onNavigate, strategies, isLoading, error, onRetry, onSelectStrategy,
}: Props) {
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

          {isLoading ? (
            <section className="flex flex-col items-center gap-2 rounded-card bg-surface px-10 py-20" aria-live="polite">
              <p className="text-lg font-semibold text-ink">투자전략을 불러오고 있어요.</p>
            </section>
          ) : error ? (
            <section className="flex flex-col items-center gap-4 rounded-card bg-surface px-10 py-20" role="alert">
              <p className="text-lg font-semibold text-ink">투자전략을 불러오지 못했어요.</p>
              <p className="text-base text-muted">{error}</p>
              {onRetry && <button onClick={onRetry} className="rounded-field bg-lime px-7 py-3 text-base font-bold text-navy">다시 시도하기</button>}
            </section>
          ) : strategies.length === 0 ? (
            <section className="flex flex-col items-center gap-2 rounded-card bg-surface px-10 py-20">
              <p className="text-lg font-semibold text-ink">아직 준비된 투자전략이 없어요.</p>
              <p className="text-base text-muted">곧 새로운 전략으로 찾아올게요.</p>
            </section>
          ) : (
            <div className="grid grid-cols-3 gap-6">
              {strategies.map((s) => (
                <button
                  key={s.id}
                  onClick={() => onSelectStrategy(s.id)}
                  className="group flex flex-col justify-between gap-10 rounded-card bg-surface p-9 text-left shadow-[0_0_0_1px_#E5E9E3_inset] transition-shadow hover:shadow-[0_0_0_1px_#C9D1C4_inset,0_12px_28px_rgba(24,36,58,0.06)]"
                >
                  <div className="flex flex-col gap-3">
                    <span className="text-[21px] font-bold tracking-[-0.02em] text-ink">{s.name}</span>
                    <p className="text-[16px] leading-[26px] text-muted">{s.description}</p>
                  </div>
                  <span className="text-[15px] font-semibold text-muted transition-colors group-hover:text-navy">
                    자세히 보기 →
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
