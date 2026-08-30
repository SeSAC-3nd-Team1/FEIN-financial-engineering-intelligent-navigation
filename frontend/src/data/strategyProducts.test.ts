import { describe, expect, it } from 'vitest';
import { F4_SUB_STRATEGIES } from './strategyProducts';

describe('F4 strategy availability', () => {
  it('keeps momentum as the sole MVP-available strategy, listed first', () => {
    // 정책 변경: F4 MVP 실제 이용 가능 대상이 이벤트 드리븐 -> 모멘텀으로 교체됨.
    const statusById = Object.fromEntries(
      F4_SUB_STRATEGIES.map((strategy) => [strategy.id, strategy.status]),
    );

    expect(statusById['f4-momentum']).toBe('available');
    expect(statusById['f4-event-driven']).toBe('testing');
    expect(statusById['f4-value']).toBe('testing');
    expect(statusById['f4-stat-arb']).toBe('testing');
    expect(F4_SUB_STRATEGIES[0].id).toBe('f4-momentum');
  });
});
