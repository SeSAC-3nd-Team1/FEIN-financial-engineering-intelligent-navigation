import type { BacktestPeriod } from '../types';

/**
 * 추천 기간 프리셋 — MOCK.
 * 코로나 폭락 / 2022 하락장의 정확한 시작·종료일은 데이터팀이 보유 데이터와
 * 한국 증시 기준으로 확정할 예정이며, 아래 날짜는 그 전까지 쓰는 placeholder다.
 * 실 데이터 연동 시 이 파일 안의 날짜만 교체하면 된다(다른 곳에 하드코딩하지 않는다).
 */
export const USE_MOCK_PERIODS = true;

// MOCK — 실제 급락/약세장 구간으로 확정된 날짜가 아님
const STATIC_PERIODS: BacktestPeriod[] = [
  {
    id: 'corona-crash',
    label: '코로나 폭락',
    startDate: '2020-01-20',
    endDate: '2020-06-30',
    description: '시장이 급격하게 하락했던 시기에 이 전략이 얼마나 버텼는지 확인해보세요.',
  },
  {
    id: 'downturn-2022',
    label: '2022 하락장',
    startDate: '2022-01-01',
    endDate: '2022-12-30',
    description: '시장이 장기간 약세를 보였을 때 전략의 수익과 위험을 확인해보세요.',
  },
];

/** '최근 5년'은 고정 날짜가 아니라 매번 오늘 기준으로 계산한다(하드코딩하면 곧 stale해짐) */
function recentFiveYearsPeriod(): BacktestPeriod {
  const end = new Date();
  const start = new Date(end);
  start.setFullYear(start.getFullYear() - 5);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return {
    id: 'recent-5y',
    label: '최근 5년',
    startDate: iso(start),
    endDate: iso(end),
    description: '상승과 하락을 포함한 장기적인 성과를 확인해보세요.',
  };
}

/** 3개 추천 기간 프리셋. 실 API 연동 시 이 함수 내부만 실제 fetch 로 교체하면 된다. */
export function getRecommendedPeriods(): BacktestPeriod[] {
  return [...STATIC_PERIODS, recentFiveYearsPeriod()];
}

/** 백테스트가 지원하는 데이터 범위 — 직접 기간 설정 검증에 쓴다(다른 곳에 하드코딩하지 않는다) */
export const AVAILABLE_DATA_RANGE = {
  minDate: '2015-01-01',
  maxDate: new Date().toISOString().slice(0, 10),
};

/** 직접 기간 설정 값 검증 — 문제 없으면 null, 문제 있으면 사용자에게 보여줄 메시지 */
export function validateCustomPeriod(startDate: string, endDate: string): string | null {
  if (!startDate || !endDate) return '시작일과 종료일을 모두 선택해주세요.';
  if (startDate >= endDate) return '시작일은 종료일보다 이전이어야 해요.';
  if (endDate > AVAILABLE_DATA_RANGE.maxDate) return '미래 날짜는 선택할 수 없어요.';
  if (startDate < AVAILABLE_DATA_RANGE.minDate) return '이 기간에는 사용할 수 있는 데이터가 없어요.';
  return null;
}
