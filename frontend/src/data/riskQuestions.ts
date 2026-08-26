/** id 는 백엔드 설문 카탈로그(backend/app/domain/investor_profile/questionnaire.py, QUESTIONNAIRE_V1)의
 *  question_id/option_id 와 1:1로 맞춰뒀다 — /investor-profile/analyze 호출 시 이 id 를 그대로 보낸다. */
export interface RiskOption { id: string; title: string; desc?: string; }
export interface RiskQuestion {
  /** 백엔드 questionnaire_version="v1" 문항 id */
  id: string;
  q: string;
  support?: string;
  options: RiskOption[];
  /** Review 화면(입력 내용 확인)에서 쓰는 짧은 라벨 */
  reviewLabel: string;
  /** Review 화면에서 이 문항을 묶는 그룹 제목 */
  reviewGroup: string;
}

const GROUP_EXPERIENCE = '투자 경험과 이해도';
const GROUP_GOAL = '투자 목표와 성향';
const GROUP_FINANCE = '재무 정보';

/** 투자자 정보 확인 8문항 — 한 화면에 한 질문. 문항/보기 문구는 기획 원문을 그대로 사용한다 */
export const RISK_QUESTIONS: RiskQuestion[] = [
  {
    id: 'investment_experience',
    q: '투자를 해본 경험이 얼마나 있나요?',
    reviewLabel: '투자 경험',
    reviewGroup: GROUP_EXPERIENCE,
    options: [
      { id: 'none', title: '처음이에요' },
      { id: 'under_1_year', title: '1년 미만' },
      { id: '1_to_3_years', title: '1~3년' },
      { id: '3_to_5_years', title: '3~5년' },
      { id: 'over_5_years', title: '5년 이상' },
    ],
  },
  {
    id: 'product_knowledge',
    q: '주식이나 펀드 같은 투자상품을 얼마나 이해하고 있나요?',
    reviewLabel: '금융상품 이해도',
    reviewGroup: GROUP_EXPERIENCE,
    options: [
      { id: 'very_low', title: '거의 몰라요' },
      { id: 'basic', title: '기본적인 내용은 알아요' },
      { id: 'intermediate', title: '어느 정도 이해하고 있어요' },
      { id: 'advanced', title: '다양한 투자상품을 잘 이해하고 있어요' },
    ],
  },
  {
    id: 'investment_horizon',
    q: '이번 투자는 얼마나 오래 이어갈 생각인가요?',
    reviewLabel: '투자 기간',
    reviewGroup: GROUP_GOAL,
    options: [
      { id: 'under_1_year', title: '1년 미만' },
      { id: '1_to_3_years', title: '1~3년' },
      { id: '3_to_5_years', title: '3~5년' },
      { id: 'over_5_years', title: '5년 이상' },
    ],
  },
  {
    id: 'investment_goal',
    q: '이번 투자의 가장 큰 목적은 무엇인가요?',
    reviewLabel: '투자 목적',
    reviewGroup: GROUP_GOAL,
    options: [
      { id: 'living_expenses', title: '생활에 필요한 자금 마련' },
      { id: 'major_purchase', title: '주택·결혼 등 목돈 마련' },
      { id: 'retirement', title: '노후 준비' },
      { id: 'surplus_management', title: '여유자금 운용' },
      { id: 'long_term_growth', title: '장기적인 자산 증식' },
    ],
  },
  {
    id: 'loss_tolerance',
    q: '투자할 돈이 줄어들더라도 어느 정도까지 감당할 수 있나요?',
    support: '퍼센트는 투자 원금 기준이에요.',
    reviewLabel: '감당 가능한 손실',
    reviewGroup: GROUP_GOAL,
    options: [
      { id: 'no_loss', title: '원금 손실을 원하지 않아요' },
      { id: 'loss_10_percent', title: '10% 정도의 손실까지 괜찮아요' },
      { id: 'loss_20_percent', title: '20% 정도의 손실까지 괜찮아요' },
      { id: 'loss_30_percent', title: '30% 정도의 손실까지 괜찮아요' },
      { id: 'loss_over_30_percent', title: '더 큰 손실도 감수할 수 있어요' },
    ],
  },
  {
    id: 'risk_return_preference',
    q: '수익과 안정성 중 어디에 더 가까운 투자를 원하나요?',
    reviewLabel: '수익 / 안정성 선호',
    reviewGroup: GROUP_GOAL,
    options: [
      { id: 'principal_preservation', title: '원금 보존이 가장 중요해요' },
      { id: 'stability', title: '안정성을 더 중요하게 생각해요' },
      { id: 'balanced', title: '안정성과 수익을 비슷하게 생각해요' },
      { id: 'return', title: '수익을 더 중요하게 생각해요' },
      { id: 'high_return', title: '높은 수익을 위해 큰 변동도 감수할 수 있어요' },
    ],
  },
  {
    id: 'investable_asset_ratio',
    q: '현재 가진 금융자산 중 이번 투자에 사용할 금액은 어느 정도인가요?',
    support: '예금, 주식, 펀드 등 보유 금융자산을 기준으로 생각해주세요.',
    reviewLabel: '투자 가능 자산 비중',
    reviewGroup: GROUP_FINANCE,
    options: [
      { id: 'under_10_percent', title: '10% 미만' },
      { id: '10_to_30_percent', title: '10~30%' },
      { id: '30_to_50_percent', title: '30~50%' },
      { id: '50_to_70_percent', title: '50~70%' },
      { id: 'over_70_percent', title: '70% 이상' },
    ],
  },
  {
    id: 'annual_income',
    q: '연간 소득은 어느 정도인가요?',
    support: '투자자 정보를 확인하고 적합한 투자전략을 안내하는 데 활용돼요.',
    reviewLabel: '연간소득',
    reviewGroup: GROUP_FINANCE,
    options: [
      { id: 'under_10m', title: '1천만원 미만' },
      { id: '10m_to_30m', title: '1천만원 이상 ~ 3천만원 미만' },
      { id: '30m_to_50m', title: '3천만원 이상 ~ 5천만원 미만' },
      { id: '50m_to_80m', title: '5천만원 이상 ~ 8천만원 미만' },
      { id: 'over_80m', title: '8천만원 이상' },
    ],
  },
];
