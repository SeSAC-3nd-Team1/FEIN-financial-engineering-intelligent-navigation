import { useEffect, useMemo, useRef, useState } from 'react';
import { ImageOff, X } from 'lucide-react';
import {
  ApiError, getCarGoalApi, upsertCarGoalApi, type CarGrade,
} from '../lib/backendApi';
import { useTradingData } from '../hooks/useTradingData';
import { digitsOnly, won } from '../lib/validation';
import { useAuthStore } from '../store/authStore';
import { useTradingStore } from '../store/tradingStore';

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

function GoalAmountField({ value, onChange }: { value: number; onChange: (next: number) => void }) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);

  const commit = () => {
    const n = Math.min(MAX_AMOUNT, Number(digitsOnly(text, 12) || '0'));
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

type LoadStatus = 'loading' | 'ready' | 'error';

export default function CarGoalProgress() {
  const accessToken = useAuthStore((s) => s.accessToken);
  // Portfolio/Dashboard와 같은 훅·스토어를 그대로 써서 "나의 투자"(portfolio.total_assets)를
  // 그대로 가져온다 — "현재 투자 금액"은 여기서 직접 입력받지 않고 항상 이 값을 따라간다.
  useTradingData();
  const portfolio = useTradingStore((s) => s.portfolio);
  const reducedMotion = usePrefersReducedMotion();
  const [broken, setBroken] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [saveError, setSaveError] = useState(false);
  // "변경" 버튼을 눌렀을 때만 등급 선택 카드를 펼친다 — 평소엔 현재 등급 한 줄 요약만 보여
  // 화면이 두 카드로 항상 붐비지 않게 한다. 아직 한 번도 고른 적 없으면(grade=null) 요약할
  // 값 자체가 없으므로 펼친 상태를 강제한다.
  const [pickerOpen, setPickerOpen] = useState(false);
  // 목표 금액도 등급 카드와 같은 원칙 — 평소엔 "목표: OO원 · 수정" 한 줄만 보여주고,
  // "수정"을 눌렀을 때만 실제 입력창을 연다. 자주 안 바뀌는 값이 매번 큰 입력창을 차지하지
  // 않게 한다.
  const [goalEditing, setGoalEditing] = useState(false);

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
    setGoalEditing(false);
    if (grade) persist({ grade, goalAmount: next, currentAmount });
  };
  const setCurrentAmount = (next: number) => {
    setCurrentAmountState(next);
    if (grade) persist({ grade, goalAmount, currentAmount: next });
  };

  // 계좌가 없거나 아직 포지션이 없으면 total_assets 도 0이다 — 그대로 0으로 둔다(별도 목업 없음).
  const livePortfolioAmount = portfolio ? Number(portfolio.total_assets) : 0;
  useEffect(() => {
    if (status !== 'ready') return;
    if (livePortfolioAmount === currentAmount) return;
    setCurrentAmount(livePortfolioAmount);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [livePortfolioAmount, status]);

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
    <section className="flex min-h-0 w-full flex-1 flex-col gap-4 rounded-card bg-surface p-6 shadow-elevation-sm">
      {/* Portfolio.tsx의 "나의 포트폴리오" 제목처럼 카드 제목은 항상 상단에 고정한다(shrink-0) —
          카드 전체를 seros-center로 묶으면 제목이 카드 한가운데로 떠 보여 어색해진다. 늘어난
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
          </div>
        </div>
      )}

      {/* 2~4. 카드 폭이 Portfolio 메인 컨텐츠(1040px)와 통일되면서 세로로만 쌓으면 이미지가 넓고
          납작해진다 — 이미지(왼쪽 고정폭)와 진행률/금액 정보(오른쪽)를 한 카드 안에서 좌우로
          나눠 넓은 폭을 자연스럽게 쓴다. 등급을 아직 한 번도 고르지 않았으면(grade=null) 통째로
          숨긴다. */}
      {grade !== null && (
        <div className="flex min-h-0 flex-1 flex-col gap-6 sm:flex-row sm:items-stretch">
          {/* 2~3. 차량 이미지 — 카드가 늘어난 만큼 이미지도 함께 커져서(고정 높이 대신 flex-1 +
              min/max 범위) 카드 안에 빈 공간이 남지 않게 한다. 폭은 계속 고정해 좌우 배치가
              흔들리지 않는다. 두 레이어를 겹쳐 크로스페이드하며, 등급 이름은 좌측 상단,
              "변경"은 우측 상단에 얹는다. */}
          <div className="relative h-full min-h-[240px] w-full shrink-0 overflow-hidden rounded-[20px] bg-canvas sm:w-[420px] sm:max-h-[440px]">
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

          <div className="flex flex-1 flex-col justify-center gap-7">
            {/* 3.5. 물방개 — 진행률(%) 위쪽 빈 공간을 상시 채운다. 박스로 감싸면 오히려 튀어
                보여서, 카드 배경 위에 그대로 얹는다(Chatbot.tsx 빈 대화 상태와 같은 방식) —
                이미지 살짝 겹치게, 말풍선 없이 문구만 옆에 자연스럽게 둔다. 달성 전에는
                응원하는 말투, 달성하면 character-celebrate.png의 축하 연출과 맞춰 문구도
                축하로 바뀐다. */}
            <div className="flex items-center gap-5">
              <img src="/character-celebrate.png" alt="" aria-hidden="true" className="h-[220px] w-[220px] shrink-0 object-contain" />
              <span className="flex-1 text-center whitespace-pre-line text-[26px] font-bold leading-9 tracking-[-0.02em]">
                {completed ? '물방개도 함께\n축하하고 있어요!' : '물방개가 목표 달성을\n응원 해요!'}
              </span>
            </div>

            {/* 4. 진행률/메시지 — 이 위젯을 열었을 때 가장 먼저 눈에 들어와야 할 "결과"라서 맨 위.
                카드가 커진 만큼 글자/바 두께도 함께 키워 빈 여백 대신 내용 자체가 채우게 한다. */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between text-base font-semibold text-muted">
                <span>
                  {completed
                    ? '목표 금액을 달성했어요! 🎉'
                    : goalAmount > 0
                      ? `${won(goalAmount - currentAmount)} 더 모으면 목표를 달성해요.`
                      : '목표 금액을 입력해주세요.'}
                </span>
                <span className="text-xl font-bold text-navy">{Math.round(progress)}%</span>
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

            {/* 5. 목표 금액 — 평소엔 "목표: OO원 · 수정" 한 줄만 보이고, "수정"을 눌렀을 때만
                입력창을 연다(값을 정하면 다시 한 줄로 접힌다). */}
            {goalEditing ? (
              <GoalAmountField value={goalAmount} onChange={setGoalAmount} />
            ) : (
              <div className="flex items-center justify-between rounded-field bg-canvas px-5 py-4">
                <div className="flex flex-col gap-1">
                  <span className="text-sm text-muted">목표 금액</span>
                  <span className="text-2xl font-bold tracking-[-0.02em]">{won(goalAmount)}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setGoalEditing(true)}
                  className="shrink-0 rounded-full px-3.5 py-2 text-sm font-bold text-navy underline decoration-[#C6F04D] decoration-2 underline-offset-2"
                >
                  수정
                </button>
              </div>
            )}

            {/* 6. 현재 투자 금액 — 직접 손댈 수 없는 값이라 입력창처럼 보이지 않게 가볍게 한 줄로만 둔다. */}
            <div className="flex items-center justify-between text-base">
              <span className="text-muted">현재 투자 금액</span>
              <span className="font-semibold text-ink">
                {won(currentAmount)} <span className="text-[13px] font-medium text-subtle">(포트폴리오 연동)</span>
              </span>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
