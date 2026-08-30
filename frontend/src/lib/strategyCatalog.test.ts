import { describe, expect, it } from 'vitest';
import type { StrategyResponse } from './backendApi';
import { resolvePortfolioStrategy, strategyRebalanceLabel, strategyRiskLabel } from './strategyCatalog';

const low: StrategyResponse = {
  id: 'low',
  name: '안정형',
  description: 'low',
  risk_level: 'LOW',
  rebalance_cycle: 'MONTHLY',
};

const high: StrategyResponse = {
  id: 'high',
  name: '공격형',
  description: 'high',
  risk_level: 'HIGH',
  rebalance_cycle: 'WEEKLY',
};

describe('strategy catalog 표시값', () => {
  it('Backend enum을 사용자 문구로 변환한다', () => {
    expect(strategyRiskLabel('MEDIUM')).toBe('보통');
    expect(strategyRebalanceLabel('QUARTERLY')).toBe('분기 1회');
  });

  it('새로운 enum은 임의 fallback으로 바꾸지 않고 원문을 보존한다', () => {
    expect(strategyRiskLabel('VERY_HIGH')).toBe('VERY_HIGH');
    expect(strategyRebalanceLabel('DAILY')).toBe('DAILY');
  });
});

describe('portfolio strategy source of truth', () => {
  it('탐색 strategyId와 달라도 실제 계좌 selected_strategy_id를 우선한다', () => {
    expect(resolvePortfolioStrategy([low, high], low, 'high')).toEqual(high);
  });

  it('계좌 조회 전에는 기존 탐색 전략으로 렌더링을 이어간다', () => {
    expect(resolvePortfolioStrategy([low, high], low, undefined)).toEqual(low);
  });

  it('실제 계좌 전략이 없거나 카탈로그에 없으면 임의 fallback하지 않는다', () => {
    expect(resolvePortfolioStrategy([low, high], low, null)).toBeNull();
    expect(resolvePortfolioStrategy([low, high], low, 'removed-strategy')).toBeNull();
  });
});
