import { useEffect, useRef, useState } from 'react';
import {
  ApiError, getCarGoalApi, upsertCarGoalApi, type CarGrade,
} from '../lib/backendApi';
import { useAuthStore } from '../store/authStore';
import { useTradingStore } from '../store/tradingStore';
import { useTradingData } from './useTradingData';

const DEFAULT_GOAL = 30_000_000;
export const CAR_GOAL_MAX_AMOUNT = 2_000_000_000; // 20억원 — 백엔드 CarGoalUpsertRequest의 le 상한과 맞춘다

export type CarGoalStatus = 'loading' | 'ready' | 'error';

/** "목표 차량" 상태(등급/목표·현재 금액)를 계정 단위로 불러오고 저장한다 — Home.tsx 상단 요약과
 *  CarGoalProgress 카드가 같은 값을 보도록 이 훅 하나로 두 곳에 상태를 공급한다(Home.tsx가
 *  한 번만 호출해 CarGoalProgress에는 props로 내려준다 — 각자 따로 부르면 fetch가 두 번
 *  일어나고, 한쪽에서 수정해도 다른 쪽이 안 바뀌는 상태 불일치가 생긴다). */
export function useCarGoal() {
  const accessToken = useAuthStore((s) => s.accessToken);
  // Portfolio/Dashboard와 같은 훅·스토어를 그대로 써서 "나의 투자"(portfolio.total_assets)를
  // 그대로 가져온다 — "현재 투자 금액"은 여기서 직접 입력받지 않고 항상 이 값을 따라간다.
  useTradingData();
  const portfolio = useTradingStore((s) => s.portfolio);

  const [status, setStatus] = useState<CarGoalStatus>('loading');
  const [saveError, setSaveError] = useState(false);

  // grade=null: 서버에 아직 저장된 값이 없다고 "확인된" 상태(계정당 최초 진입) — 로딩 중에는 아직
  // 모르는 상태이므로 이 값만으로 게이트를 그리지 않고 반드시 status==='ready'와 함께 본다.
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
  const progress = goalAmount > 0 ? Math.min(100, Math.max(0, (currentAmount / goalAmount) * 100)) : 0;
  const completed = progress >= 100;

  /** 등급/금액 중 하나가 바뀔 때마다 세 값을 함께 서버에 저장한다 — upsert가 항상 세 값을 통째로 받는
   *  구조라, 화면 상태를 먼저 반영(낙관적 업데이트)하고 실패하면 인라인 에러로 알린다. */
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

  // Portfolio.tsx의 "나의 투자" 옆 수익률과 같은 값(백엔드가 계산해 둔 계좌 손익률)을 그대로 쓴다.
  // 계좌가 없으면(portfolio=null) 0%로 둔다 — Portfolio.tsx와 달리 여기선 계좌 없음 상태의
  // 목업 수익률을 보여줄 이유가 없다(목표 차량 위젯 자체가 실제 투자 진행을 보여주는 용도).
  const returnPct = portfolio ? Number(portfolio.return_rate) : 0;

  // 계좌가 없거나 아직 포지션이 없으면 total_assets 도 0이다 — 그대로 0으로 둔다(별도 목업 없음).
  const livePortfolioAmount = portfolio ? Number(portfolio.total_assets) : 0;
  useEffect(() => {
    if (status !== 'ready') return;
    if (livePortfolioAmount === currentAmount) return;
    setCurrentAmount(livePortfolioAmount);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [livePortfolioAmount, status]);

  return {
    status, saveError, grade, goalAmount, currentAmount, returnPct, progress, completed, setGrade, setGoalAmount,
  };
}

export type UseCarGoalResult = ReturnType<typeof useCarGoal>;
