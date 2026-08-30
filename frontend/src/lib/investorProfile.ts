import type { InvestorProfileResponse } from './backendApi';
import { RISK_QUESTIONS } from '../data/riskQuestions';

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
  /** 0~100 최종 위험 점수. 점수 도입 전 v1 결과는 null이다. */
  riskScore: number | null;
  tendencyLine: string;
  description: string;
  traits: InvestorTraits;
}

/** 백엔드 POST /investor-profile/analyze · GET /investor-profile/me/latest 응답(snake_case traits)을
 *  화면이 실제로 쓰는 InvestorProfileResult 모양으로 맞춘다. */
export function mapInvestorProfileResponse(response: InvestorProfileResponse): InvestorProfileResult {
  return {
    type: response.profile_type,
    riskScore: response.risk_score ?? null,
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
