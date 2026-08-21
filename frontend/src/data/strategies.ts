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

/** 백테스트 구간 — 03 전략 상세의 기간 선택 */
export interface Scenario {
  id: string; label: string; period: string; amount: number;
  strat: number[]; kospi: number[]; stratEnd: number; kospiEnd: number;
  headline: string; body: string;
}

export const SCENARIOS: Scenario[] = [
  {
    id: 'corona', label: '코로나 폭락', period: '2020.01 – 2020.06', amount: 10_000_000,
    strat: [0, -2, -5, -9, -14, -17, -15, -11, -8, -5, -3, -1],
    kospi: [0, -4, -11, -19, -28, -32, -28, -22, -17, -12, -8, -5],
    stratEnd: -17, kospiEnd: -32,
    headline: '폭락장에서 시장보다 15%p 덜 떨어졌어요',
    body: '많이 흔들리는 종목의 비중을 낮게 유지해서, 시장 전체보다 충격을 덜 받았어요.',
  },
  {
    id: 'rate', label: '2022 금리인상', period: '2022.01 – 2022.12', amount: 10_000_000,
    strat: [0, -3, -6, -8, -11, -13, -12, -14, -16, -13, -10, -8],
    kospi: [0, -5, -9, -14, -19, -23, -21, -25, -28, -24, -20, -17],
    stratEnd: -8, kospiEnd: -17,
    headline: '금리가 오르는 동안에도 시장보다 9%p 덜 빠졌어요',
    body: '이익이 꾸준한 기업 위주로 담아서, 금리 부담이 큰 성장주보다 덜 흔들렸어요.',
  },
  {
    id: 'full', label: '전체 5년', period: '2021.01 – 2026.06', amount: 10_000_000,
    strat: [0, 8, 14, 9, 18, 26, 22, 31, 38, 44, 51, 58],
    kospi: [0, 6, 11, 4, 12, 19, 14, 21, 26, 30, 35, 41],
    stratEnd: 58, kospiEnd: 41,
    headline: '5년 동안 시장보다 17%p 더 벌었어요',
    body: '크게 떨어지는 구간을 덜 겪으면서 회복이 빨랐고, 그 차이가 시간이 지날수록 벌어졌어요.',
  },
];
