import { useEffect, useMemo, useRef, useState } from 'react';
import { ImageOff } from 'lucide-react';
import { digitsOnly, won } from '../lib/validation';

type CarGrade = 'inex' | 'highend';

const GRADES: { id: CarGrade; label: string; description: string }[] = [
  { id: 'inex', label: '보급차', description: '가볍게 시작하는 실속형 목표' },
  { id: 'highend', label: '고급차', description: '조금 더 크게 그려보는 목표' },
];

/** 진행률 구간별 이미지 파일 번호(01~06) — 등급별로 같은 번호의 이미지를 쓴다.
 *  파일은 frontend/public 루트에 `Inex_01.png`~`Inex_06.png`, `highend_01.png`~`highend_06.png`로 있다. */
const STAGE_THRESHOLDS = [0, 10, 30, 50, 70, 90] as const;
const GRADE_FILE_PREFIX: Record<CarGrade, string> = { inex: 'Inex', highend: 'highend' };

const STORAGE_KEY = 'fein.car-goal-progress';
const DEFAULT_GOAL = 30_000_000;
const MAX_AMOUNT = 2_000_000_000; // 20억원 — 입력 폭주 방지용 상한, 실사용 범위를 넉넉히 덮는다
const CROSSFADE_MS = 650;

interface StoredState {
  grade: CarGrade;
  goalAmount: number;
  currentAmount: number;
}

function loadStored(): StoredState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) throw new Error('empty');
    const parsed = JSON.parse(raw) as Partial<StoredState>;
    return {
      grade: parsed.grade === 'highend' ? 'highend' : 'inex',
      goalAmount: Number.isFinite(parsed.goalAmount) && (parsed.goalAmount ?? 0) > 0 ? Number(parsed.goalAmount) : DEFAULT_GOAL,
      currentAmount: Number.isFinite(parsed.currentAmount) && (parsed.currentAmount ?? 0) >= 0 ? Number(parsed.currentAmount) : 0,
    };
  } catch {
    return { grade: 'inex', goalAmount: DEFAULT_GOAL, currentAmount: 0 };
  }
}

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

export default function CarGoalProgress() {
  const [{ grade, goalAmount, currentAmount }, setState] = useState<StoredState>(loadStored);
  const reducedMotion = usePrefersReducedMotion();
  const [broken, setBroken] = useState<Record<string, boolean>>({});

  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ grade, goalAmount, currentAmount }));
  }, [grade, goalAmount, currentAmount]);

  // 목표가 0원이면(입력 중 등) 0%로 취급한다 — 0으로 나누는 상황을 만들지 않는다.
  const progress = useMemo(
    () => (goalAmount > 0 ? Math.min(100, Math.max(0, (currentAmount / goalAmount) * 100)) : 0),
    [currentAmount, goalAmount],
  );
  const completed = progress >= 100;

  // 등급을 바꿔도 같은 진행률에 대응하는 이미지로 즉시 넘어간다 — 목표/현재 금액은 그대로 유지된다.
  const target = imagePathFor(grade, progress);
  const { back, front, frontVisible } = useCrossfadeImage(target, CROSSFADE_MS, reducedMotion);

  const setGrade = (next: CarGrade) => setState((s) => ({ ...s, grade: next }));
  const setGoalAmount = (next: number) => setState((s) => ({ ...s, goalAmount: next }));
  const setCurrentAmount = (next: number) => setState((s) => ({ ...s, currentAmount: next }));

  const markBroken = (src: string) => setBroken((prev) => (prev[src] ? prev : { ...prev, [src]: true }));
  const bothBroken = broken[back] && broken[front];

  return (
    <section className="flex w-full max-w-[560px] flex-col gap-6 rounded-card bg-surface p-8 shadow-[0_0_0_1px_#E5E9E3_inset]">
      <div className="flex flex-col gap-1">
        <span className="text-sm font-semibold text-muted">목표 차량</span>
        <h2 className="text-2xl font-bold tracking-[-0.025em]">투자가 쌓일수록 목표 차량에 가까워져요</h2>
      </div>

      {/* 1. 차량 등급 선택 — 카드 2개 중 하나를 고르는 방식 */}
      <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-label="차량 등급 선택">
        {GRADES.map((g) => {
          const active = grade === g.id;
          return (
            <div
              key={g.id}
              className={`relative flex flex-col gap-1 rounded-field p-4 text-left transition-shadow ${
                active ? 'bg-[#F8FCEE] shadow-[0_0_0_2px_#C6F04D_inset]' : 'bg-canvas shadow-[0_0_0_1px_#E5E9E3_inset]'
              }`}
            >
              <button
                type="button"
                role="radio"
                aria-checked={active}
                aria-label={`${g.label} — ${g.description}`}
                onClick={() => setGrade(g.id)}
                className="absolute inset-0 rounded-field"
              />
              <span className="pointer-events-none text-base font-bold tracking-[-0.02em]">{g.label}</span>
              <span className="pointer-events-none text-[13px] text-muted">{g.description}</span>
            </div>
          );
        })}
      </div>

      {/* 2~3. 차량 이미지 — 두 레이어를 겹쳐 크로스페이드한다. 컨테이너 크기는 고정이라 전환 중에도
          이미지 크기/위치가 흔들리지 않는다. */}
      <div className="relative h-56 w-full overflow-hidden rounded-[20px] bg-canvas">
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
      </div>
    </section>
  );
}
