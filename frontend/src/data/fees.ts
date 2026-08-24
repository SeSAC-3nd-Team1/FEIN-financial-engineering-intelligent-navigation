/**
 * 운용 방식별 이용 수수료 — MOCK.
 * 실제 서비스 요율이 아니라 프로토타입을 위한 가상 정책이며,
 * 출시 전 정책/법무 검토를 거쳐 확정해야 한다.
 * UI 여러 곳에 값을 흩어두지 않도록 이 한 곳에서만 관리한다.
 */
export const USE_MOCK_FEES = true;

export type OperationMode = 'manual' | 'auto';

export const INVESTMENT_FEES: Record<OperationMode, number> = {
  manual: 0.008, // 확인하고 실행 — 연 0.8%
  auto: 0.012,   // 자동으로 운용 — 연 1.2%
};

/** 투자금액 기준 예상 연간 수수료(원) — Math.round 로 원 단위 반올림 */
export const estimateAnnualFee = (investmentAmount: number, mode: OperationMode): number =>
  Math.round(investmentAmount * INVESTMENT_FEES[mode]);
