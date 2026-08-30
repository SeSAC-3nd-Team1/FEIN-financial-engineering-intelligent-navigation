import { useEffect, useRef, useState } from 'react';
import { ImageOff, X } from 'lucide-react';
import { CAR_GOAL_MAX_AMOUNT, type UseCarGoalResult } from '../hooks/useCarGoal';
import { digitsOnly, won } from '../lib/validation';
import type { CarGrade } from '../lib/backendApi';

const GRADES: { id: CarGrade; label: string; description: string }[] = [
  { id: 'INEX', label: '다마방개', description: '가볍게 시작하는 실속형 목표' },
  { id: 'HIGHEND', label: '람브로방개', description: '조금 더 크게 그려보는 목표' },
];

/** 진행률 구간별 이미지 파일 번호(01~06) — 등급별로 같은 번호의 이미지를 쓴다.
 *  파일은 frontend/public 루트에 `Inex_01.png`~`Inex_06.png`, `highend_01.png`~`highend_06.png`로 있다. */
const STAGE_THRESHOLDS = [0, 10, 30, 50, 70, 90] as const;
const GRADE_FILE_PREFIX: Record<CarGrade, string> = { INEX: 'Inex', HIGHEND: 'highend' };

const CROSSFADE_MS = 650;

function stageIndexFor(progress: number) {
  return STAGE_THRESHOLDS.reduce<number>((stage, threshold, index) => (progress >= threshold ? index : stage), 0);
}

function imagePathFor(grade: CarGrade, progress: number) {
  const stageNumber = stageIndexFor(progress) + 1; // 1~6
  return `/${GRADE_FILE_PREFIX[grade]}_${String(stageNumber).padStart(2, '0')}.png`;
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    const mql = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setReduced(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

/** target이 바뀔 때마다 "지금 보이던 이미지(back)" 위에 "새 이미지(front)"를 opacity 0→1로 겹쳐
 *  페이드인시켜 크로스페이드를 낸다. 전환 도중 target이 또 바뀌어도 그 시점의 front를 back으로
 *  스냅샷하고 다시 시작하므로 전환이 겹치거나 끊겨 보이지 않는다. */
function useCrossfadeImage(target: string, durationMs: number, reducedMotion: boolean) {
  const [pair, setPair] = useState(() => ({ back: target, front: target, frontVisible: true }));
  const timerRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (pair.front === target) return;

    if (timerRef.current != null) window.clearTimeout(timerRef.current);
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);

    if (reducedMotion) {
      setPair({ back: target, front: target, frontVisible: true });
      return;
    }

    setPair((prev) => ({ back: prev.front, front: target, frontVisible: false }));
    rafRef.current = requestAnimationFrame(() => {
      setPair((prev) => (prev.front === target ? { ...prev, frontVisible: true } : prev));
    });
    timerRef.current = window.setTimeout(() => {
      setPair((prev) => (prev.front === target ? { back: target, front: target, frontVisible: true } : prev));
    }, durationMs + 30);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, durationMs, reducedMotion]);

  useEffect(
    () => () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    },
    [],
  );

  return pair;
}

function GoalAmountField({ value, onChange }: { value: number; onChange: (next: number) => void }) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);

  const commit = () => {
    const parsed = Number(digitsOnly(text, 12) || '0');
    // 입력칸을 비우고(혹은 0으로) 벗어나면 이전 값으로 되돌린다 — 목표 금액 0원은 진행률/카드
    // 문구가 전부 의미를 잃는 상태라("목표 금액을 입력해주세요"처럼 사용자 흐름상 막다른 상태),
    // 애초에 그 상태에 들어가지 않게 막는다.
    const n = parsed > 0 ? Math.min(CAR_GOAL_MAX_AMOUNT, parsed) : value;
    onChange(n);
    setText(String(n));
  };

  return (
    <label className="flex flex-col gap-2">
      <span className="text-sm font-semibold text-muted">목표 금액</span>
      <div className="flex items-center gap-2 rounded-field bg-surface px-4 py-3.5 shadow-[0_0_0_1px_#E5E9E3_inset] focus-within:shadow-[0_0_0_2px_#C6F04D_inset]">
        <input
          value={Number(text || '0').toLocaleString('ko-KR')}
          inputMode="numeric"
          onChange={(e) => setText(digitsOnly(e.target.value, 12))}
          onBlur={commit}
          onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
          className="w-full bg-transparent text-lg font-bold tracking-[-0.02em] outline-none"
        />
        <span className="shrink-0 text-base font-semibold text-muted">원</span>
      </div>
    </label>
  );
}

/** 상태/데이터는 useCarGoal()에서 받는다 — Home.tsx가 훅을 한 번만 불러 상단 요약과 이 카드에
 *  같은 값을 내려준다(각자 따로 fetch하면 두 곳이 어긋날 수 있다). */
export default function CarGoalProgress(props: UseCarGoalResult) {
  const {
    status, saveError, grade, goalAmount, currentAmount, progress, completed, setGrade, setGoalAmount,
  } = props;
  const reducedMotion = usePrefersReducedMotion();
  const [broken, setBroken] = useState<Record<string, boolean>>({});
  // "변경" 버튼을 눌렀을 때만 등급 선택 카드를 펼친다 — 평소엔 현재 등급 한 줄 요약만 보여
  // 화면이 두 카드로 항상 붐비지 않게 한다. 아직 한 번도 고른 적 없으면(grade=null) 요약할
  // 값 자체가 없으므로 펼친 상태를 강제한다.
  const [pickerOpen, setPickerOpen] = useState(false);

  // 등급을 바꿔도 같은 진행률에 대응하는 이미지로 즉시 넘어간다 — 목표/현재 금액은 그대로 유지된다.
  // grade가 아직 null(최초 미선택/로딩 중)이어도 훅은 항상 같은 순서로 호출되어야 하므로 무해한
  // 기본값으로 계산해두고, 아래 렌더에서 필요할 때만 이 이미지 섹션을 보여준다.
  const target = imagePathFor(grade ?? 'INEX', progress);
  const { back, front, frontVisible } = useCrossfadeImage(target, CROSSFADE_MS, reducedMotion);

  // "변경" 팝업에서 등급을 골라도 곧장 닫지 않는다 — 같은 팝업 안에서 목표 금액도 이어서
  // 바꿀 수 있어야 하므로, 닫는 것은 X 버튼(또는 최초 선택 시엔 등급 선택 자체)에 맡긴다.
  const handleGrade = (nextGrade: CarGrade) => setGrade(nextGrade);

  const markBroken = (src: string) => setBroken((prev) => (prev[src] ? prev : { ...prev, [src]: true }));
  const bothBroken = broken[back] && broken[front];

  if (status === 'loading') {
    return (
      <section className="flex min-h-0 w-full flex-1 flex-col justify-center gap-2 rounded-card bg-surface p-6 shadow-elevation-sm">
        <span className="text-sm font-semibold text-muted">목표 차량</span>
        <div className="h-40 w-full animate-pulse rounded-[20px] bg-canvas" />
      </section>
    );
  }

  if (status === 'error') {
    return (
      <section className="flex min-h-0 w-full flex-1 flex-col justify-center gap-2 rounded-card bg-surface p-6 shadow-elevation-sm">
        <span className="text-sm font-semibold text-muted">목표 차량</span>
        <p className="text-base font-semibold text-muted">목표 차량 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.</p>
      </section>
    );
  }

  return (
    <section className="flex min-h-0 w-full flex-1 flex-col gap-3 rounded-card bg-surface p-5 shadow-elevation-sm">
      {/* Portfolio.tsx의 "나의 포트폴리오" 제목처럼 카드 제목은 항상 상단에 고정한다(shrink-0) —
          카드 전체를 justify-center로 묶으면 제목이 카드 한가운데로 떠 보여 어색해진다. 늘어난
          세로 공간은 아래 차량/진행률 블록만 flex-1로 받아 그 안에서 중앙 정렬한다. */}
      <div className="flex shrink-0 flex-col gap-0.5">
        <span className="text-[13px] font-semibold text-muted">목표 차량</span>
        <h2 className="text-lg font-bold tracking-[-0.02em]">투자가 쌓일수록 목표 차량에 가까워져요</h2>
      </div>

      {/* 1. 차량 등급 — 평소엔 이미지 위 라벨("현재 등급"/"변경")로만 존재해 화면을 차분하게 두고,
          "변경"을 누르거나(또는 grade=null인 최초 진입) 팝업을 띄워 그 중 하나를 고르게 한다.
          최초 진입(grade=null)에는 필수 선택이라 배경 클릭/닫기 버튼으로 닫을 수 없다. */}
      {(grade === null || pickerOpen) && (
        <div
          className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8"
          onClick={() => { if (grade !== null) setPickerOpen(false); }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="차량 등급 선택"
            className="flex w-[480px] flex-col gap-6 rounded-card bg-surface p-10"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-6">
              <div className="flex flex-col gap-2">
                <h3 className="text-[22px] font-bold tracking-[-0.025em]">차량 등급을 선택해주세요</h3>
                <p className="text-sm text-muted">
                  {grade === null ? '최초 1회 필수 선택이에요. 이후 언제든 바꿀 수 있어요.' : '선택한 등급의 차량 이미지로 진행률을 보여드려요.'}
                </p>
              </div>
              {grade !== null && (
                <button
                  type="button"
                  aria-label="닫기"
                  onClick={() => setPickerOpen(false)}
                  className="rounded-[9px] bg-canvas p-2 text-muted"
                >
                  <X size={18} />
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-required={grade === null} aria-label="차량 등급 선택">
              {GRADES.map((g) => {
                const active = grade === g.id;
                return (
                  <button
                    key={g.id}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => handleGrade(g.id)}
                    className={`flex flex-col gap-1 rounded-field p-4 text-left transition-shadow ${
                      active ? 'bg-[#F8FCEE] shadow-[0_0_0_2px_#C6F04D_inset]' : 'bg-canvas shadow-[0_0_0_1px_#E5E9E3_inset]'
                    }`}
                  >
                    <span className="text-base font-bold tracking-[-0.02em]">{g.label}</span>
                    <span className="text-[13px] text-muted">{g.description}</span>
                  </button>
                );
              })}
            </div>

            {/* 목표 금액도 같은 팝업에서 바꾼다 — 카드 본문에 따로 두면 등급과 다른 곳에서
                고쳐야 해 번거롭고, "변경" 버튼 하나로 등급/금액을 한 번에 관리하게 한다. */}
            <GoalAmountField value={goalAmount} onChange={setGoalAmount} />
          </div>
        </div>
      )}

      {/* 2~6. 차량 이미지를 카드 상단에 넓게 두고, 그 아래 진행 정보를 세로로 쌓는다 — 좌우로
          쪼개면 이미지가 좁은 고정폭에 갇혀 존재감이 작아지므로, 카드 폭(1040px)을 이미지가
          그대로 받게 하고 진행률/금액 정보는 그 아래 전체 폭을 쓰는 한 줄씩으로 둔다. 등급을
          아직 한 번도 고르지 않았으면(grade=null) 통째로 숨긴다. */}
      {grade !== null && (
        <div className="flex min-h-0 flex-1 flex-col gap-4">
          {/* 2~3. 차량 이미지 — 카드가 늘어난 만큼 이미지도 함께 커져서(고정 높이 대신 flex-1 +
              min/max 범위) 카드 안에 빈 공간이 남지 않게 한다. 두 레이어를 겹쳐 크로스페이드하며,
              등급 이름은 좌측 상단, "변경"은 우측 상단에 얹는다. min-h를 낮춰 작은 화면(768px대
              높이)에서도 아래 진행률/금액 정보와 함께 스크롤 없이 들어가게 한다. */}
          <div className="relative min-h-[140px] w-full flex-1 overflow-hidden rounded-[20px] bg-canvas sm:max-h-[380px]">
            <div className="absolute left-3 top-3 z-20 rounded-full bg-surface/90 px-3 py-1.5 text-[13px] font-bold text-navy shadow-[0_0_0_1px_#E5E9E3_inset]">
              {GRADES.find((g) => g.id === grade)?.label}
            </div>
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className="absolute right-3 top-3 z-20 rounded-full bg-surface/90 px-3 py-1.5 text-[13px] font-bold text-navy underline decoration-[#C6F04D] decoration-2 underline-offset-2 shadow-[0_0_0_1px_#E5E9E3_inset]"
            >
              변경
            </button>
            {bothBroken ? (
              <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-subtle">
                <ImageOff size={28} />
                <span className="text-sm font-semibold">차량 이미지를 불러오지 못했어요</span>
              </div>
            ) : (
              <>
                <img
                  src={back}
                  alt=""
                  aria-hidden="true"
                  onError={() => markBroken(back)}
                  className="absolute inset-0 h-full w-full object-contain p-6"
                />
                {front !== back && (
                  <img
                    key={front}
                    src={front}
                    alt={`${GRADES.find((g) => g.id === grade)?.label} 목표 달성 진행 이미지`}
                    onError={() => markBroken(front)}
                    className="absolute inset-0 h-full w-full object-contain p-6 transition-[opacity,transform] ease-out"
                    style={{
                      opacity: frontVisible ? 1 : 0,
                      transform: frontVisible ? 'translateY(0) scale(1)' : 'translateY(6px) scale(0.98)',
                      transitionDuration: reducedMotion ? '0ms' : `${CROSSFADE_MS}ms`,
                    }}
                  />
                )}
              </>
            )}
          </div>

          {/* 4. 물방개 + 진행률/메시지 — 마스코트가 진행 메시지를 직접 전하듯 아이콘과 문구를
              한 줄에 두고, 퍼센트는 오른쪽 끝, 그 아래 진행률 바를 카드 전체 폭으로 이어 붙인다. */}
          <div className="flex shrink-0 flex-col gap-2">
            <div className="flex items-center gap-5">
              <img src="/character-celebrate.png" alt="" aria-hidden="true" className="h-[84px] w-[84px] shrink-0 object-contain" />
              <div className="flex flex-1 items-center justify-between gap-4">
                <span className="text-lg font-bold tracking-[-0.02em]">
                  {completed
                    ? '목표 금액을 달성했어요! 🎉'
                    : goalAmount > 0
                      ? `${won(goalAmount - currentAmount)} 더 모으면 목표를 달성해요.`
                      : '"변경" 버튼을 눌러 목표 금액을 설정해주세요.'}
                </span>
                <span className="shrink-0 text-2xl font-bold text-navy">{Math.round(progress)}%</span>
              </div>
            </div>
            <div className="h-3.5 overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full bg-lime transition-[width] duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            {saveError && (
              <p className="text-[13px] font-semibold text-warn">저장하지 못했어요. 네트워크를 확인해주세요.</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
