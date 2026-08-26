import type { Strategy } from '../data/strategies';
import { getStrategiesApi, type StrategyResponse } from './backendApi';

const RISK_LABEL: Record<string, string> = { LOW: '낮음', MEDIUM: '보통', HIGH: '높음' };
const REBALANCE_LABEL: Record<string, string> = {
  WEEKLY: '주 1회', MONTHLY: '월 1회', QUARTERLY: '분기 1회', YEARLY: '연 1회',
};

/** 실 카탈로그(GET /strategies, public, 모델 무관)의 name/risk_level/rebalance_cycle로 정적 Strategy를
 *  최신화한다. tagline/why/suitabilityNote(마케팅 카피)와 match/annual/mdd/vol/sharpe(백테스트 대표값 —
 *  어느 기간을 "대표"로 볼지 정책이 아직 없음)는 실 대응 데이터가 없어 그대로 둔다. */
export function applyStrategyCatalog(base: Strategy, real: StrategyResponse): Strategy {
  return {
    ...base,
    name: real.name,
    risk: RISK_LABEL[real.risk_level] ?? base.risk,
    rebalance: REBALANCE_LABEL[real.rebalance_cycle] ?? base.rebalance,
  };
}

/** 실패하면(네트워크 오류 등) null을 돌려준다 — 호출부가 기존 정적 STRATEGIES를 그대로 쓰면 된다. */
export async function fetchStrategyCatalog(): Promise<StrategyResponse[] | null> {
  try {
    return await getStrategiesApi();
  } catch {
    return null;
  }
}
