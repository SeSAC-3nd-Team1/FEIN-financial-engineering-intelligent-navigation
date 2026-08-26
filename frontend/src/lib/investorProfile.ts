import type { InvestorProfileResponse } from './backendApi';
import { RISK_QUESTIONS } from '../data/riskQuestions';

/**
 * MOCK 투자성향 분류 로직 — 실제 금융투자상품 적합성·적정성 판단 기준이 아니다.
 * 자본시장법상 요구되는 문항 설계·배점·투자자유형 분류 체계는 별도로 검증되어야 하며,
 * 여기서는 서비스 UX/데모 목적의 임의 로직만 사용한다.
 */
export interface InvestorTraits {
  /** 안정성 선호 — 1~5 (dot 채움 개수) */
  stability: number;
  /** 수익추구 성향 — 1~5 */
  returnSeeking: number;
  /** 투자기간 성향 — 1~5 */
  horizon: number;
}

export interface InvestorProfileResult {
  type: string;
  tendencyLine: string;
  description: string;
  traits: InvestorTraits;
}

const HORIZON_DOTS = [1, 2, 4, 5]; // Q3(4지선다) 인덱스 → 5단계 dot

/** answers: 7문항 각각 고른 보기의 인덱스 (0-based) */
export function computeInvestorProfile(answers: number[]): InvestorProfileResult {
  const [experience, , horizonIdx, , lossToleranceIdx, riskPrefIdx] = answers;

  const stability = 5 - lossToleranceIdx; // 손실 감내가 낮을수록 안정성 dot이 높음
  const returnSeeking = riskPrefIdx + 1; // 수익 선호가 높을수록 dot이 높음
  const horizon = HORIZON_DOTS[horizonIdx] ?? 3;

  // MOCK: 손실감내 + 위험/수익 선호를 더한 값으로 5단계 버킷을 나눈다 (0~8)
  const riskScore = lossToleranceIdx + riskPrefIdx;

  if (riskScore <= 1) {
    return {
      type: '안정추구형',
      tendencyLine: '지키는 것을 가장 중요하게 생각하는 투자자예요',
      description: '큰 변동 없이 원금을 지키는 것을 최우선으로 생각해요. 수익보다는 안정적인 흐름을 선호해요.',
      traits: { stability, returnSeeking, horizon },
    };
  }
  if (riskScore <= 3) {
    return {
      type: '안정투자형',
      tendencyLine: '안정성을 더 중요하게 생각하는 투자자예요',
      description: '작은 변동은 감수할 수 있지만, 그래도 안정적인 흐름 안에서 조금씩 불려가는 쪽을 선호해요.',
      traits: { stability, returnSeeking, horizon },
    };
  }
  if (riskScore <= 5) {
    return {
      type: '중립투자형',
      tendencyLine: '균형을 중요하게 생각하는 투자자예요',
      description: '큰 변동을 감수하며 높은 수익을 추구하기보다는 적당한 위험 안에서 꾸준한 자산 성장을 선호해요.',
      traits: { stability, returnSeeking, horizon },
    };
  }
  if (riskScore <= 7) {
    return {
      type: '성장추구형',
      tendencyLine: '수익을 더 중요하게 생각하는 투자자예요',
      description: '안정성보다는 수익에 더 무게를 둬요. 어느 정도의 변동은 자산을 키우는 과정으로 받아들일 수 있어요.',
      traits: { stability, returnSeeking, horizon },
    };
  }
  return {
    type: '공격투자형',
    tendencyLine: '높은 수익을 위해 변동을 적극적으로 감수하는 투자자예요',
    description: '큰 변동이 있더라도 그 안에서 기회를 찾는 쪽을 선호해요. 수익 잠재력을 안정성보다 우선해요.',
    traits: { stability, returnSeeking, horizon },
  };
}

/** 투자성향 유형 → AI 추천 전략 id — RiskResult "AI가 가장 추천해요" 카드가 이 매핑을 따른다.
 *  실제 추천 로직/데이터가 붙기 전까지의 MOCK 매핑이다. */
const STRATEGY_BY_PROFILE_TYPE: Record<string, string> = {
  '안정추구형': 'low',
  '안정투자형': 'low',
  '중립투자형': 'value',
  '성장추구형': 'momentum',
  '공격투자형': 'momentum',
};

export function recommendedStrategyId(type: string): string {
  return STRATEGY_BY_PROFILE_TYPE[type] ?? 'low';
}

/** 백엔드 POST /investor-profile/analyze · GET /investor-profile/me/latest 응답(snake_case traits)을
 *  화면이 실제로 쓰는 InvestorProfileResult 모양으로 맞춘다 — 이 값이 진단 결과의 Source of Truth이고,
 *  computeInvestorProfile()의 로컬 계산은 이 API 호출이 실패했을 때만 쓰는 fallback이다. */
export function mapInvestorProfileResponse(response: InvestorProfileResponse): InvestorProfileResult {
  return {
    type: response.profile_type,
    tendencyLine: response.tendency_line,
    description: response.description,
    traits: {
      stability: response.traits.stability,
      returnSeeking: response.traits.return_seeking,
      horizon: response.traits.horizon,
    },
  };
}

/** answers(문항별로 고른 보기 인덱스) → 백엔드 POST /investor-profile/analyze 가 기대하는
 *  { question_id, option_id } 배열로 변환한다. RISK_QUESTIONS 는 백엔드 설문 카탈로그
 *  (app/domain/investor_profile/questionnaire.py, QUESTIONNAIRE_V1)와 문항 순서·id 가 1:1로 맞춰져 있다. */
export function buildInvestorAnswerPayload(answers: number[]): { question_id: string; option_id: string }[] {
  return RISK_QUESTIONS.map((question, i) => ({
    question_id: question.id,
    option_id: question.options[answers[i]].id,
  }));
}

/** 결과·확인 화면에서 원문 보기를 다시 보여줄 때 쓰는 헬퍼 */
export function answerLabel(questionIndex: number, optionIndex: number | null | undefined): string {
  if (optionIndex == null) return '-';
  return RISK_QUESTIONS[questionIndex]?.options[optionIndex]?.title ?? '-';
}

/**
 * MOCK 전략 적합도 라벨 — data/strategies.ts의 고정 match(%) 값을 구간화해
 * "몇 % 정확히 맞다" 같은 과장된 수치 대신 이해하기 쉬운 문구로 보여준다.
 */
export function matchLabel(match: number): string {
  if (match >= 90) return '나와 잘 맞아요';
  if (match >= 75) return '비교적 잘 맞아요';
  return '조금 더 확인이 필요해요';
}
