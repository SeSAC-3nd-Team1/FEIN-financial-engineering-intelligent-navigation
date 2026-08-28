import { useEffect, useMemo, useRef, useState } from 'react';
import { ImageOff } from 'lucide-react';
import {
  ApiError, getCarGoalApi, upsertCarGoalApi, type CarGrade,
} from '../lib/backendApi';
import { digitsOnly, won } from '../lib/validation';
import { useAuthStore } from '../store/authStore';

const GRADES: { id: CarGrade; label: string; description: string }[] = [
  { id: 'INEX', label: '보급차', description: '가볍게 시작하는 실속형 목표' },
  { id: 'HIGHEND', label: '고급차', description: '조금 더 크게 그려보는 목표' },
];

/** 진행률 구간별 이미지 파일 번호(01~06) — 등급별로 같은 번호의 이미지를 쓴다.
 *  파일은 frontend/public 루트에 `Inex_01.png`~`Inex_06.png`, `highend_01.png`~`highend_06.png`로 있다. */
const STAGE_THRESHOLDS = [0, 10, 30, 50, 70, 90] as const;
const GRADE_FILE_PREFIX: Record<CarGrade, string> = { INEX: 'Inex', HIGHEND: 'highend' };

const DEFAULT_GOAL = 30_000_000;
const MAX_AMOUNT = 2_000_000_000; // 20억원 — 백엔드 CarGoalUpsertRequest의 le 상한과 맞춘다
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

function AmountField({
  label, value, onChange,
}: { label: string; value: number; onChange: (next: number) => void }) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);

  const commit = () => {
    const n = Math.min(MAX_AMOUNT, Number(digitsOnly(text, 12) || '0'));
    onChange(n);
    setText(String(n));
  };

  return (
    <label className="flex flex-1 flex-col gap-2">
      <span className="text-sm font-semibold text-muted">{label}</span>
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

type LoadStatus = 'loading' | 'ready' | 'error';

export default function CarGoalProgress() {
  const accessToken = useAuthStore((s) => s.accessToken);
  const reducedMotion = usePrefersReducedMotion();
  const [broken, setBroken] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [saveError, setSaveError] = useState(false);
  // "변경" 버튼을 눌렀을 때만 등급 선택 카드를 펼친다 — 평소엔 현재 등급 한 줄 요약만 보여
  // 화면이 두 카드로 항상 붐비지 않게 한다. 아직 한 번도 고른 적 없으면(grade=null) 요약할
  // 값 자체가 없으므로 펼친 상태를 강제한다.
  const [pickerOpen, setPickerOpen] = useState(false);

  // grade=null: 서버에 아직 저장된 값이 없다고 "확인된" 상태(계정당 최초 진입) — 로딩 중에는 아직
  // 모르는 상태이므로 이 값만으로 게이트를 그리지 않고 반드시 status===\'ready\'와 함께 본다.
  const [grade, setGradeState] = useState<CarGrade | null>(null);
  const [goalAmount, setGoalAmountState] = useState(DEFAULT_GOAL);
  const [currentAmount, setCurrentAmountState] = useState(0);

  const requestIdRef = useRef(0);

  useEffect(() => {
    if (!accessToken) return;
    const requestId = ++requestIdRef.current;
    setStatus('loading');
    getCarGoalApi(accessToken)
      .then((res) => {
        if (requestIdRef.current !== requestId) return;
        setGradeState(res.car_grade);
        setGoalAmountState(Number(res.goal_amount));
        setCurrentAmountState(Number(res.current_amount));
        setStatus('ready');
      })
      .catch((error: unknown) => {
        if (requestIdRef.current !== requestId) return;
        if (error instanceof ApiError && error.code === 'CAR_GOAL_NOT_SET') {
          // 계정 최초 진입 — 아직 아무것도 고른 적 없다는 게 "확인된" 상태. 계속 null로 둔다.
          setGradeState(null);
          setStatus('ready');
          return;
        }
        setStatus('error');
      });
  }, [accessToken]);

  // 목표가 0원이면(입력 중 등) 0%로 취급한다 — 0으로 나누는 상황을 만들지 않는다.
  const progress = useMemo(
    () => (goalAmount > 0 ? Math.min(100, Math.max(0, (currentAmount / goalAmount) * 100)) : 0),
    [currentAmount, goalAmount],
  );
  const completed = progress >= 100;

  // 등급을 바꿔도 같은 진행률에 대응하는 이미지로 즉시 넘어간다 — 목표/현재 금액은 그대로 유지된다.
  // grade가 아직 null(최초 미선택/로딩 중)이어도 훅은 항상 같은 순서로 호출되어야 하므로 무해한
  // 기본값으로 계산해두고, 아래 렌더에서 필요할 때만 이 이미지 섹션을 보여준다.
  const target = imagePathFor(grade ?? 'INEX', progress);
  const { back, front, frontVisible } = useCrossfadeImage(target, CROSSFADE_MS, reducedMotion);

  /** 등급/금액 중 하나가 바뀔 때마다 세 값을 함께 서버에 저장한다 — upsert가 항상 세 값을 통째로 받는
   *  구조라, 화면 상태를 먼저 반영(낙관적 업데이트)하고 실패하면 서버 값으로 다시 맞춘다. */
  const persist = (next: { grade: CarGrade; goalAmount: number; currentAmount: number }) => {
    if (!accessToken) return;
    setSaveError(false);
    const requestId = ++requestIdRef.current;
    upsertCarGoalApi(
      { car_grade: next.grade, goal_amount: next.goalAmount, current_amount: next.currentAmount },
      accessToken,
    ).catch(() => {
      if (requestIdRef.current !== requestId) return;
      setSaveError(true);
    });
  };

  const setGrade = (nextGrade: CarGrade) => {
    setGradeState(nextGrade);
    setPickerOpen(false);
    persist({ grade: nextGrade, goalAmount, currentAmount });
  };
  const setGoalAmount = (next: number) => {
    setGoalAmountState(next);
    if (grade) persist({ grade, goalAmount: next, currentAmount });
  };
  const setCurrentAmount = (next: number) => {
    setCurrentAmountState(next);
    if (grade) persist({ grade, goalAmount, currentAmount: next });
  };

  const markBroken = (src: string) => setBroken((prev) => (prev[src] ? prev : { ...prev, [src]: true }));
  const bothBroken = broken[back] && broken[front];

  if (status === 'loading') {
    return (
      <section className="flex w-full max-w-[560px] flex-col gap-2 rounded-card bg-surface p-8 shadow-[0_0_0_1px_#E5E9E3_inset]">
        <span className="text-sm font-semibold text-muted">목표 차량</span>
        <div className="h-56 w-full animate-pulse rounded-[20px] bg-canvas" />
      </section>
    );
  }

  if (status === 'error') {
    return (
      <section className="flex w-full max-w-[560px] flex-col gap-2 rounded-card bg-surface p-8 shadow-[0_0_0_1px_#E5E9E3_inset]">
        <span className="text-sm font-semibold text-muted">목표 차량</span>
        <p className="text-base font-semibold text-muted">목표 차량 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.</p>
      </section>
    );
  }

  return (
    <section className="flex w-full max-w-[560px] flex-col gap-6 rounded-card bg-surface p-8 shadow-[0_0_0_1px_#E5E9E3_inset]">
      <div className="flex flex-col gap-1">
        <span className="text-sm font-semibold text-muted">목표 차량</span>
        <h2 className="text-2xl font-bold tracking-[-0.025em]">투자가 쌓일수록 목표 차량에 가까워져요</h2>
        {grade === null && (
          <p className="text-sm font-semibold text-[#7A5A1E]">차량 등급을 먼저 선택해주세요. (최초 1회 필수, 이후 언제든 변경할 수 있어요)</p>
        )}
      </div>

      {/* 1. 차량 등급 — 평소엔 이미지 위 라벨("현재 등급"/"변경")로만 존재해 화면을 차분하게 두고,
          "변경"을 누르거나(또는 grade=null인 최초 진입) 카드 2개를 펼쳐 그 중 하나를 고르게 한다.
          고르는 즉시 다시 접힌다. */}
      {(grade === null || pickerOpen) && (
        <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-required={grade === null} aria-label="차량 등급 선택">
          {GRADES.map((g) => {
            const active = grade === g.id;
            return (
              <button
                key={g.id}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setGrade(g.id)}
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
      )}

      {/* 2~4. 이미지/금액 입력/진행률 — 등급을 아직 한 번도 고르지 않았으면(grade=null) 통째로 숨긴다.
          최초 선택 이후에는 항상 그려진다(등급 변경은 이미지 좌측 상단 라벨 옆 "변경"으로 계속 가능). */}
      {grade !== null && (
        <>
          {/* 2~3. 차량 이미지 — 두 레이어를 겹쳐 크로스페이드한다. 컨테이너 크기는 고정이라 전환 중에도
              이미지 크기/위치가 흔들리지 않는다. 등급 이름은 이미지 좌측 상단에, "변경"은 우측 상단에 얹는다. */}
          <div className="relative h-56 w-full overflow-hidden rounded-[20px] bg-canvas">
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

          {/* 4. 목표/현재 금액 입력 */}
          <div className="flex gap-4">
            <AmountField label="목표 금액" value={goalAmount} onChange={setGoalAmount} />
            <AmountField label="현재 투자 금액" value={currentAmount} onChange={setCurrentAmount} />
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-sm font-semibold text-muted">
              <span>
                {completed
                  ? '목표 금액을 달성했어요! 🎉'
                  : goalAmount > 0
                    ? `${won(goalAmount - currentAmount)} 더 모으면 목표를 달성해요.`
                    : '목표 금액을 입력해주세요.'}
              </span>
              <span className="text-navy">{Math.round(progress)}%</span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full bg-lime transition-[width] duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            {saveError && (
              <p className="text-[13px] font-semibold text-warn">저장하지 못했어요. 네트워크를 확인해주세요.</p>
            )}
          </div>
        </>
      )}
    </section>
  );
}
