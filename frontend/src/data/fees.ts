/**
 * 운용 방식별 이용 수수료 — MOCK.
 * 실제 서비스 요율이 아니라 프로토타입을 위한 가상 정책이며,
 * 출시 전 정책/법무 검토를 거쳐 확정해야 한다.
 * UI 여러 곳에 값을 흩어두지 않도록 이 한 곳에서만 관리한다.
 */
export const USE_MOCK_FEES = true;

export type OperationMode = 'manual' | 'auto';

/** 프론트 표기(auto/manual) → 계좌 API 표기(AUTO/SEMI_AUTO) 변환. activeMode 가 아직 없는 경우
 *  (계좌를 만들기 전)의 기본값은 반자동(SEMI_AUTO)이다 — 계좌 API 자체 기본값과도 맞춰뒀다. */
export function toAccountOperationMode(mode: OperationMode | null): 'AUTO' | 'SEMI_AUTO' {
  return mode === 'auto' ? 'AUTO' : 'SEMI_AUTO';
}

/** 계좌 API 표기(AUTO/SEMI_AUTO) → 프론트 표기(auto/manual) 역변환. 로컬(activeMode)에 없는
 *  실제 계좌 정보로 프론트 상태를 되짚어야 할 때 사용한다. */
export function toOperationMode(mode: 'AUTO' | 'SEMI_AUTO'): OperationMode {
  return mode === 'AUTO' ? 'auto' : 'manual';
}

export const INVESTMENT_FEES: Record<OperationMode, number> = {
  manual: 0.008, // 확인하고 실행 — 연 0.8%
  auto: 0.012,   // 자동으로 운용 — 연 1.2%
};

/** 투자금액 기준 예상 연간 수수료(원) — Math.round 로 원 단위 반올림 */
export const estimateAnnualFee = (investmentAmount: number, mode: OperationMode): number =>
  Math.round(investmentAmount * INVESTMENT_FEES[mode]);
