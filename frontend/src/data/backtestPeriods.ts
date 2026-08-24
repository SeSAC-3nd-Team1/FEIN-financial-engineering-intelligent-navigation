import type { BacktestPeriod } from '../types';
import type { BacktestAvailableRange } from './backtestApi';

/** 실제 KRX 데이터에서 조회할 추천 기간 프리셋이다. 데이터 미보유 기간은 Backend가 unavailable로 응답한다. */
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
function recentFiveYearsPeriod(range: BacktestAvailableRange): BacktestPeriod {
  const end = new Date(`${range.maxDate}T00:00:00Z`);
  const start = new Date(end);
  start.setFullYear(start.getFullYear() - 5);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return {
    id: 'recent-5y',
    label: '최근 5년',
    startDate: iso(start) < range.minDate ? range.minDate : iso(start),
    endDate: range.maxDate,
    description: '상승과 하락을 포함한 장기적인 성과를 확인해보세요.',
  };
}

/** 3개 추천 기간 프리셋. */
export function getRecommendedPeriods(range: BacktestAvailableRange): BacktestPeriod[] {
  const supported = STATIC_PERIODS.filter(
    (period) => period.startDate >= range.minDate && period.endDate <= range.maxDate,
  );
  return [...supported, recentFiveYearsPeriod(range)];
}

/** 직접 기간 설정 값 검증 — 문제 없으면 null, 문제 있으면 사용자에게 보여줄 메시지 */
export function validateCustomPeriod(
  startDate: string,
  endDate: string,
  range: BacktestAvailableRange,
): string | null {
  if (!startDate || !endDate) return '시작일과 종료일을 모두 선택해주세요.';
  if (startDate >= endDate) return '시작일은 종료일보다 이전이어야 해요.';
  if (endDate > range.maxDate) return '이 기간에는 사용할 수 있는 데이터가 없어요.';
  if (startDate < range.minDate) return '이 기간에는 사용할 수 있는 데이터가 없어요.';
  return null;
}
