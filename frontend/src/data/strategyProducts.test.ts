import { describe, expect, it } from 'vitest';
import { F4_SUB_STRATEGIES } from './strategyProducts';

describe('F4 strategy availability', () => {
  it('keeps event-driven and momentum available', () => {
    const statusById = Object.fromEntries(
      F4_SUB_STRATEGIES.map((strategy) => [strategy.id, strategy.status]),
    );

    expect(statusById['f4-event-driven']).toBe('available');
    expect(statusById['f4-momentum']).toBe('available');
    expect(statusById['f4-value']).toBe('testing');
    expect(statusById['f4-stat-arb']).toBe('testing');
  });
});
