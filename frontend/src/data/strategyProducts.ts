/**
 * 물·방·개 전략 체계 — Strategy Main(구 Strategy List)/F4 선택 화면/Coming Soon 화면 전용 정적 카피.
 *
 * 이 파일의 id/이름/설명은 모두 프론트엔드 전용 UI 식별자이며, 백엔드 `strategies` 테이블의 canonical
 * strategy id(`low`/`value`/`momentum`)와 무관하다. 실제 Model/Backend contract가 확정되기 전까지는
 * 어떤 API 호출에도 이 값을 사용하지 않는다 — "저변동성 = 물림방지" 같은 임의 매핑을 하지 않기 위함이다.
 */

export interface StrategyProductCard {
  key: 'loss-avoidance' | 'f4-collection' | 'personalized';
  /** 카드 제목의 첫 글자(Visual Anchor) — 물/방/개 */
  anchor: string;
  /** anchor를 제외한 나머지 전략명 */
  restOfName: string;
  name: string;
  meta: string;
  status?: 'testing';
  description: string;
  ctaLabel: string;
  /** 2차 디자인 QA — 카드별 subtle color point. 새 palette가 아니라 기존 토큰 중에서만 고른다. */
  tint: 'lime' | 'warm' | 'neutral';
}

export const STRATEGY_PRODUCT_CARDS: StrategyProductCard[] = [
  {
    key: 'loss-avoidance',
    anchor: '물',
    restOfName: '림방지 전략',
    name: '물림방지 전략',
    meta: 'FE!N 자체 알고리즘',
    description: '큰 손실을 피하면서 안정적인 투자를 지향하는 FE!N의 자체 전략입니다.',
    ctaLabel: '자세히 보기 →',
    tint: 'lime',
  },
  {
    key: 'f4-collection',
    anchor: '방',
    restOfName: '탄 F4 전략집',
    name: '방탄 F4 전략집',
    meta: '대표 투자전략 4가지',
    description: '시장에서도 활용되는 대표적인 투자 전략 4가지를 한곳에서 살펴볼 수 있어요.',
    ctaLabel: '4가지 전략 보기 →',
    tint: 'warm',
  },
  {
    key: 'personalized',
    anchor: '개',
    restOfName: '인 맞춤화 전략',
    name: '개인 맞춤화 전략',
    meta: 'Personalized Strategy',
    status: 'testing',
    description: '나의 투자 기준과 스타일을 반영해 나를 대신해 투자하는 개인화 전략을 준비하고 있어요.',
    ctaLabel: '미리 보기 →',
    tint: 'neutral',
  },
];

export interface F4SubStrategy {
  id: 'f4-value' | 'f4-momentum' | 'f4-stat-arb' | 'f4-event-driven';
  name: string;
  status: 'testing' | 'available';
  description: string;
}

/**
 * 방탄 F4 전략집 하위 4개 — 이벤트 드리븐만 MVP에서 실제 연결 대상(상세는 StrategyComingSoon 참고).
 * 2차 디자인 QA: 실제 이용 가능한 전략을 먼저 보여주는 게 자연스럽다는 피드백에 따라 이벤트
 * 드리븐을 배열 맨 앞으로 이동했다 — canonical id/데이터 구조는 그대로, display order만 변경.
 */
export const F4_SUB_STRATEGIES: F4SubStrategy[] = [
  {
    id: 'f4-event-driven', name: '이벤트 드리븐 전략', status: 'available',
    description: '공시나 뉴스 같은 시장 이벤트를 활용해 상대적으로 유리한 종목을 찾는 전략이에요.',
  },
  {
    id: 'f4-value', name: '가치주 전략', status: 'testing',
    description: '기업의 가치에 비해 상대적으로 저평가된 종목을 찾는 전략이에요.',
  },
  {
    id: 'f4-momentum', name: '모멘텀 전략', status: 'testing',
    description: '최근 가격 흐름이 강한 종목의 움직임을 활용하는 전략이에요.',
  },
  {
    id: 'f4-stat-arb', name: '통계적 차익거래 전략', status: 'testing',
    description: '종목 간 가격 관계와 통계적 패턴을 활용하는 전략이에요.',
  },
];

export const F4_COLLECTION_INTRO = {
  name: '방탄 F4 전략집',
  description: '시장에서 활용되는 대표적인 투자 전략 4가지를 살펴보세요. 이벤트 드리븐 전략은 MVP에서 실제로 이용할 수 있어요.',
};

/**
 * StrategyComingSoon 전용 카피 — 물림방지/이벤트 드리븐 모두 아직 실제 Model/API가 연결되지 않아
 * 실제 백테스트 대신 이 정적 안내 문구를 보여준다.
 * TODO(Mock/실제 Model contract 확정 후): canonical strategy id가 정해지면 이 화면 대신 기존
 * StrategyDetail(실 backtest 연동)로 교체한다.
 */
export const COMING_SOON_COPY = {
  'loss-avoidance': {
    name: '물림방지 전략',
    meta: 'FE!N 자체 알고리즘',
    description: '큰 손실을 피하면서 안정적인 투자를 지향하는 FE!N의 자체 전략입니다.',
    backLabel: '← 투자전략 목록',
  },
  'event-driven': {
    name: '이벤트 드리븐 전략',
    meta: '방탄 F4 전략집 · MVP에서 실제 이용 가능 예정',
    description: '공시나 뉴스 같은 시장 이벤트를 활용해 상대적으로 유리한 종목을 찾는 전략이에요.',
    backLabel: '← 방탄 F4 전략집',
  },
} as const;
