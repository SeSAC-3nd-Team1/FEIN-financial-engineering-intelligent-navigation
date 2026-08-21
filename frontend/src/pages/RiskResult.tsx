import { useRef, useState } from 'react';
import { Info } from 'lucide-react';
import Header from '../components/Header';
import { STRATEGIES } from '../data/strategies';
import { computeInvestorProfile, matchLabel } from '../lib/investorProfile';
import { useAuthStore } from '../store/authStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  onSelectStrategy: (id: string) => void;
}

/** 답변 없이 이 화면에 도달한 경우를 위한 안전한 기본값 (정상 플로우에서는 발생하지 않음) */
const FALLBACK_PROFILE = computeInvestorProfile([2, 1, 1, 4, 1, 2]);

/** 02 결과 — 투자성향 확인 + AI 추천 전략 + 대안 2개 */
export default function RiskResult({ userName, onNavigate, onSelectStrategy }: Props) {
  const [picked, setPicked] = useState('low');
  const [hero, ...alternatives] = STRATEGIES;

  const investorAnswers = useAuthStore((s) => s.investorAnswers);
  const profile = investorAnswers ? computeInvestorProfile(investorAnswers) : FALLBACK_PROFILE;

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-16">
          <section className="flex flex-col gap-5 pb-6">
            <span className="text-base font-semibold text-muted">투자자 정보 확인 · 완료</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
              투자성향을 확인했어요
            </h1>
            <div className="flex items-center gap-2.5">
              <span className="rounded-full bg-lime px-5 py-2.5 text-[22px] font-bold text-navy">{profile.type}이에요</span>
              <InvestorTypeInfo type={profile.type} description={profile.description} />
            </div>
          </section>

          <section className="flex flex-col gap-8">
            <div className="flex flex-col gap-3.5">
              <h2 className="text-[32px] font-bold leading-[46px] tracking-[-0.03em]">이 성향을 바탕으로 전략을 찾아봤어요</h2>
              <p className="text-lg leading-[30px] text-muted">
                AI가 답변과 전략의 과거 위험 특성을 함께 비교했어요. 추천은 참고용이고, 최종 선택은 {userName}님이 해요.
              </p>
            </div>

            <button
              onClick={() => setPicked(hero.id)}
              className={`flex flex-col gap-7 rounded-card bg-surface p-12 text-left ${
                picked === hero.id ? 'shadow-[0_0_0_2px_#C6F04D_inset]' : 'shadow-[0_0_0_1px_#E5E9E3_inset]'
              }`}
            >
              <div className="flex items-start justify-between gap-8">
                <div className="flex flex-col gap-3.5">
                  <span className="self-start rounded-full bg-lime px-3.5 py-2 text-sm font-bold text-navy">✦ AI가 가장 추천해요</span>
                  <span className="text-lg text-muted">{hero.tagline}</span>
                  <span className="text-[38px] font-bold leading-[52px] tracking-[-0.035em]">{hero.name}</span>
                  <span className="text-[22px] font-bold text-[#3F5222]">{matchLabel(hero.match)}</span>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <span className="text-[15px] text-muted">과거 5년 기준</span>
                  <span className="text-[40px] font-bold tracking-[-0.035em]">{hero.annual}</span>
                  <span className="text-base text-muted">연평균 수익률 · 위험도 {hero.risk}</span>
                </div>
              </div>

              <div className="grid grid-cols-4 gap-8 border-t border-[#F0F2ED] pb-1 pt-7">
                <Fact label="최대 손실(MDD)" value={hero.mdd} accent />
                <Fact label="변동성(연)" value={hero.vol} />
                <Fact label="샤프 지수" value={hero.sharpe} />
                <Fact label="리밸런싱" value={hero.rebalance} />
              </div>

              <div className="flex gap-5 rounded-[20px] bg-[#F8FCEE] px-9 py-8">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-lime text-lg text-navy">✦</div>
                <div className="flex flex-col gap-3">
                  <span className="text-[22px] font-bold leading-[34px] tracking-[-0.025em]">왜 {hero.name}을 추천했나요?</span>
                  <p className="max-w-[720px] text-lg leading-[30px] text-[#3F4A43]">{hero.why}</p>
                </div>
              </div>

              <span
                onClick={(e) => { e.stopPropagation(); onSelectStrategy(hero.id); }}
                className="self-start rounded-field bg-lime px-9 py-5 text-lg font-bold text-navy"
              >
                나에게 맞는 전략 보러가기 →
              </span>
            </button>

            <div className="grid grid-cols-2 gap-5">
              {alternatives.map((s) => (
                <button
                  key={s.id}
                  onClick={() => { setPicked(s.id); onSelectStrategy(s.id); }}
                  className={`flex flex-col gap-4 rounded-card bg-surface p-10 text-left ${
                    picked === s.id ? 'shadow-[0_0_0_2px_#C6F04D_inset]' : 'shadow-[0_0_0_1px_#E5E9E3_inset]'
                  }`}
                >
                  <div className="flex flex-col gap-3">
                    <span className="text-[17px] text-muted">{s.tagline}</span>
                    <span className="text-[28px] font-bold tracking-[-0.03em]">{s.name}</span>
                    <span className="text-[19px] font-bold text-[#3F4A43]">{matchLabel(s.match)}</span>
                  </div>
                  <div className="flex items-baseline gap-3">
                    <span className="text-[26px] font-bold tracking-[-0.03em]">{s.annual}</span>
                    <span className="text-base text-muted">연평균 · 위험도 {s.risk}</span>
                  </div>
                  <span className="text-base text-muted">MDD {s.mdd} · 변동성 {s.vol} · 샤프 {s.sharpe}</span>
                  <span className="text-[17px] font-semibold text-navy">자세히 보기 →</span>
                </button>
              ))}
            </div>
          </section>

          <p className="text-sm leading-[22px] text-subtle">
            ※ 백테스트 수익률은 과거 데이터 기반 예시이며 미래 수익을 보장하지 않습니다.
          </p>
        </div>
      </main>
    </div>
  );
}

function Fact({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[15px] text-muted">{label}</span>
      <span className={`text-[22px] font-bold ${accent ? 'text-down' : ''}`}>{value}</span>
    </div>
  );
}

/**
 * 투자유형 옆 Info 아이콘 — hover/click(desktop), tap(mobile), focus(keyboard) 모두에서 열린다.
 * 상세 설명은 여기서만 보여주고 기본 화면에는 노출하지 않는다.
 */
function InvestorTypeInfo({ type, description }: { type: string; description: string }) {
  // hover가 실제로 가능한 입력장치(마우스)에서만 hover로 연다 — 터치는 hover가 없으므로 click(tap)만으로 토글한다.
  const [hoverCapable] = useState(
    () => typeof window !== 'undefined' && window.matchMedia?.('(hover: hover) and (pointer: fine)').matches,
  );
  const [open, setOpen] = useState(false);
  // click/tap은 항상 focus를 함께 일으키는데, focus만으로 열어버리면 클릭 토글과 상태가 꼬인다.
  // pointerdown 시점에 표시해두고, 그 focus는 "포인터가 일으킨 focus"로 판단해 무시한다 —
  // 남는 focus 이벤트(Tab 키 이동)만 진짜 키보드 접근으로 취급한다.
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
          // 데스크톱은 hover가 이미 열고 mouseleave가 닫아주므로 click은 "열림 보장"만 한다(토글하면 hover 중 클릭 시 바로 닫혀버림).
          // hover가 없는 터치 기기에서는 click(tap)이 유일한 열고 닫는 수단이라 토글로 동작해야 한다.
          if (hoverCapable) { setOpen(true); return; }
          setOpen((o) => !o);
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
