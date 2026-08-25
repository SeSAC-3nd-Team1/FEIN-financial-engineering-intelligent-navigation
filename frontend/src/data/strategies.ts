export interface Strategy {
  id: 'low' | 'value' | 'momentum';
  name: string;
  tagline: string;
  match: number;      // 나와 맞는 정도 %
  annual: string;
  risk: string;
  mdd: string;
  vol: string;
  sharpe: string;
  rebalance: string;
  why: string;
}

/** Strategy List 카드용 최소 요약 — 백테스트/위험도 등 상세 지표는 의도적으로 제외한다(모델 확정 전) */
export interface StrategySummary {
  id: Strategy['id'];
  name: string;
  shortDescription: string;
}

export const STRATEGIES: Strategy[] = [
  {
    id: 'low', name: '저변동성 전략', tagline: '큰 손실은 줄이고, 꾸준히 투자하고 싶다면',
    match: 92, annual: '+10.2%', risk: '보통',
    mdd: '-18.6%', vol: '12.4%', sharpe: '0.82', rebalance: '월 1회',
    why: '손실 감내 수준이 "보통"이고 투자 기간이 긴 편이라, 시장이 흔들릴 때 방어하면서도 장기 수익을 기대할 수 있는 전략을 먼저 골랐어요.',
  },
  {
    id: 'value', name: '가치 전략', tagline: '가격보다 기업의 가치를 중요하게 본다면',
    match: 84, annual: '+11.6%', risk: '보통',
    mdd: '-24.1%', vol: '15.8%', sharpe: '0.71', rebalance: '분기 1회',
    why: '이익이나 자산 대비 저평가된 종목을 담아요. 회복까지 시간이 걸릴 수 있지만 장기 성과가 안정적인 편이에요.',
  },
  {
    id: 'momentum', name: '모멘텀 전략', tagline: '상승 흐름을 적극적으로 따라가고 싶다면',
    match: 71, annual: '+14.1%', risk: '높음',
    mdd: '-31.5%', vol: '21.3%', sharpe: '0.66', rebalance: '월 1회',
    why: '최근 오르고 있는 종목을 따라 담아요. 수익 기회가 크지만 방향이 바뀔 때 손실도 함께 커져요.',
  },
];

/** Strategy List 페이지용 — STRATEGIES에서 카드에 필요한 필드만 뽑아 쓴다(단일 소스 유지) */
export const STRATEGY_SUMMARIES: StrategySummary[] = STRATEGIES.map(({ id, name, tagline }) => ({
  id, name, shortDescription: tagline,
}));
