import { describe, expect, it } from 'vitest';
import { MIN_SIGNUP_AGE, calculateAge, meetsMinimumSignupAge } from './validation';

/** 오늘 기준 만 `age`세가 되는 YYMMDD를 만든다 — 하드코딩된 연도로 인한 시간 경과 시 테스트 깨짐을 방지한다. */
function birthdateForAge(age: number): string {
  const today = new Date();
  const year = today.getFullYear() - age;
  const yy = String(year % 100).padStart(2, '0');
  const mm = String(today.getMonth() + 1).padStart(2, '0');
  const dd = String(today.getDate()).padStart(2, '0');
  return `${yy}${mm}${dd}`;
}

describe('calculateAge', () => {
  it('returns null for an invalid format', () => {
    expect(calculateAge('abcdef')).toBeNull();
    expect(calculateAge('12345')).toBeNull();
  });

  it('infers the century so a 2-digit year never resolves to the future', () => {
    // "900101" 입력 시 2090년이 아니라 1990년으로 해석되어야 한다.
    expect(calculateAge('900101')).toBeGreaterThan(30);
  });

  it('computes the exact age for a birthdate matching today', () => {
    expect(calculateAge(birthdateForAge(20))).toBe(20);
  });
});

describe('meetsMinimumSignupAge', () => {
  it('rejects applicants younger than the minimum signup age', () => {
    expect(meetsMinimumSignupAge(birthdateForAge(10))).toBe(false);
  });

  it('accepts applicants at or above the minimum signup age', () => {
    expect(meetsMinimumSignupAge(birthdateForAge(MIN_SIGNUP_AGE))).toBe(true);
    expect(meetsMinimumSignupAge(birthdateForAge(30))).toBe(true);
  });
});
