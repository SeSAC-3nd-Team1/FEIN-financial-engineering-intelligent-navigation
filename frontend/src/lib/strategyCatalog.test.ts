import { describe, expect, it } from 'vitest';
import { strategyRebalanceLabel, strategyRiskLabel } from './strategyCatalog';

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
