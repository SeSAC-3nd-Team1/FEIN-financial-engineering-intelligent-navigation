import { INVESTMENT_FEES, type OperationMode } from './fees';

export interface OperatingModeInfo {
  id: OperationMode;
  /** 화면 전반에서 쓰는 정식 명칭 */
  label: string;
  /** 계좌 준비 화면처럼 짧은 문맥에서 쓰는 축약형 */
  shortLabel: string;
  /** 카드 배지 문구 — "초보/고수" 등 등급화 표현 금지, 판단 부담을 줄여주는 방식이라는 관점 유지 */
  recommendation: string;
  /** 카드 내 mini-flow */
  flow: string[];
  /** 계좌 준비 화면 등에서 쓰는 한 줄 설명 */
  description: string;
  feeRate: number;
}

/**
 * 운용방식 공용 정보 — label/추천문구/flow/설명/수수료를 한 곳에서 관리한다.
 * 화면마다 "확인하고 실행"/"자동으로 운용" 문자열을 따로 하드코딩하지 않고 이 config를 참조한다.
 * account.operatingMode 같은 백엔드 필드가 아직 없어 PoC 범위에서는 프론트 mock(investmentStore)에서만
 * 사용하지만, id가 실제 API의 operating_mode 값과 그대로 맞물릴 수 있게 설계했다.
 */
export const OPERATING_MODES: Record<OperationMode, OperatingModeInfo> = {
  auto: {
    id: 'auto',
    label: '자동으로 운용',
    shortLabel: '자동운용',
    recommendation: '처음이라면 추천',
    flow: ['물방개가 관리해요', '자동 실행'],
    description: '물방개가 선택한 전략에 따라 자동으로 운용해요. 투자 판단을 매번 직접 하지 않아도 돼요.',
    feeRate: INVESTMENT_FEES.auto,
  },
  manual: {
    id: 'manual',
    label: '확인하고 실행',
    shortLabel: '확인하고 실행',
    recommendation: '직접 확인하고 싶다면 추천',
    flow: ['물방개가 제안해요', '내가 확인해요', '실행'],
    description: '물방개가 투자안을 제안하면 내용을 직접 확인한 뒤 실행 여부를 결정해요.',
    feeRate: INVESTMENT_FEES.manual,
  },
};

/** 화면에 카드/목록을 그릴 때 쓰는 표시 순서 — 자동으로 운용이 항상 먼저 */
export const OPERATING_MODE_ORDER: OperationMode[] = ['auto', 'manual'];
