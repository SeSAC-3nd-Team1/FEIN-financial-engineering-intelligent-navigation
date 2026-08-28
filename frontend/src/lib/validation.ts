/** 회원가입 검증 규칙 — 프런트/백엔드가 같은 정규식을 공유한다 */
export const RE = {
  birthdate: /^\d{6}$/,                                                    // YYMMDD
  phone: /^0\d{9,10}$/,                                                    // 숫자만
  userId: /^[A-Za-z0-9]{6,16}$/,                                           // 영문+숫자 6~16자
  password: /^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$/, // 8자 이상, 영문+숫자+특수문자
  email: /^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$/,
} as const;

export const digitsOnly = (v: string, max: number) => v.replace(/[^\d]/g, '').slice(0, max);
export const won = (n: number) => `${Math.round(n).toLocaleString('ko-KR')}원`;

/** 미성년자(만 19세 미만, 민법상 성년 기준)는 법정대리인 동의 없이 서비스 이용계약을 체결할 수
 *  없다(민법 제5조). FE!N 가입 흐름에는 법정대리인 동의 절차가 없어, 가입 가능한 최소 연령을
 *  만 19세로 둔다. */
export const MIN_SIGNUP_AGE = 19;

/** YYMMDD의 2자리 연도는 세기 구분이 없으므로, 20YY로 해석했을 때 미래 날짜가 되면 19YY로 본다. */
function birthdateToDate(birthdate: string): Date | null {
  if (!RE.birthdate.test(birthdate)) return null;
  const yy = Number(birthdate.slice(0, 2));
  const mm = Number(birthdate.slice(2, 4));
  const dd = Number(birthdate.slice(4, 6));
  const today = new Date();
  const asY2000 = new Date(2000 + yy, mm - 1, dd);
  // JS Date는 존재하지 않는 날짜(예: 021332, 990230)를 다음 달/해로 자동 보정한다 — 입력한
  // month/day가 그대로 반영됐는지 확인해 보정된 값은 무효로 처리한다. 백엔드(services/auth.py의
  // _calculate_age)는 Python date() 생성이 그대로 실패하는 방식으로 이미 이렇게 동작하므로, 여기서
  // 걸러내지 않으면 프런트는 통과시키고 백엔드만 거부하는 케이스가 생긴다.
  if (asY2000.getMonth() !== mm - 1 || asY2000.getDate() !== dd) return null;
  const year = asY2000.getTime() > today.getTime() ? 1900 + yy : 2000 + yy;
  return new Date(year, mm - 1, dd);
}

/** YYMMDD 문자열로부터 만 나이를 계산한다. 형식이 올바르지 않으면 null. */
export function calculateAge(birthdate: string): number | null {
  const born = birthdateToDate(birthdate);
  if (!born) return null;
  const today = new Date();
  let age = today.getFullYear() - born.getFullYear();
  const hadBirthdayThisYear =
    today.getMonth() > born.getMonth() ||
    (today.getMonth() === born.getMonth() && today.getDate() >= born.getDate());
  if (!hadBirthdayThisYear) age -= 1;
  return age;
}

export function meetsMinimumSignupAge(birthdate: string): boolean {
  const age = calculateAge(birthdate);
  return age !== null && age >= MIN_SIGNUP_AGE;
}
