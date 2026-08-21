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
