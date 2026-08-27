/**
 * 물·방·개 전략 체계 — Strategy Main(구 Strategy List)/F4 선택 화면/Coming Soon 화면 전용 정적 카피.
 *
 * 이 파일의 id/이름/설명은 모두 프론트엔드 전용 UI 식별자이며, 백엔드 `strategies` 테이블의 canonical
 * strategy id(`low`/`value`/`momentum`)와 기본적으로 무관하다. 단, `f4-momentum`은 실제 Model/Backend
 * contract가 확정된 canonical `momentum` 전략으로 명시적으로 연결한다.
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
  /** CTA 라벨(화살표 문자 제외) — 화살표는 카드에서 별도의 lime circular arrow로 렌더링한다 */
  ctaLabel: string;
}

/**
 * 3차 디자인 QA: 물/방/개 각각 다른 색(green/yellow/blue)을 쓰던 2차 tint 시스템을 걷어내고,
 * FE!N lime key color 하나만 accent로 쓴다 — 3개 카드 모두 동일한 처리(CTA arrow circle)라
 * 카드마다 다른 색이 생기지 않는다.
 */
export const STRATEGY_PRODUCT_CARDS: StrategyProductCard[] = [
  {
    key: 'loss-avoidance',
    anchor: '물',
    restOfName: '림방지 전략',
    name: '물림방지 전략',
    meta: 'FE!N 자체 알고리즘',
    description: '큰 손실을 피하면서 안정적인 투자를 지향하는 FE!N의 자체 전략입니다.',
    ctaLabel: '자세히 보기',
  },
  {
    key: 'f4-collection',
    anchor: '방',
    restOfName: '탄 F4 전략집',
    name: '방탄 F4 전략집',
    meta: '대표 투자전략 4가지',
    description: '시장에서도 활용되는 대표적인 투자 전략 4가지를 한곳에서 살펴볼 수 있어요.',
    ctaLabel: '4가지 전략 보기',
  },
  {
    key: 'personalized',
    anchor: '개',
    restOfName: '인 맞춤화 전략',
    name: '개인 맞춤화 전략',
    meta: 'Personalized Strategy',
    status: 'testing',
    description: '나의 투자 기준과 스타일을 반영해 나를 대신해 투자하는 개인화 전략을 준비하고 있어요.',
    ctaLabel: '미리 보기',
  },
];

export interface F4SubStrategy {
  id: 'f4-value' | 'f4-momentum' | 'f4-stat-arb' | 'f4-event-driven';
  name: string;
  status: 'testing' | 'available';
  description: string;
}

/**
 * 방탄 F4 전략집 하위 4개 — MVP 실제 연결 대상이 이벤트 드리븐 → 모멘텀으로 변경됨. 모멘텀은
 * canonical 백엔드 `momentum` 전략/백테스트/추천 API에 실제로 연결되어 있어(App.tsx의
 * onSelectAvailableStrategy 구현 참고) StrategyComingSoon을 거치지 않고 바로 실 StrategyDetail로
 * 이동한다. 모멘텀을 배열 맨 앞으로, 이벤트 드리븐은 다른 테스트 중 전략과 같은 자리로 이동했다 —
 * canonical id/데이터 구조는 그대로, status·display order만 변경.
 */
export const F4_SUB_STRATEGIES: F4SubStrategy[] = [
  {
    id: 'f4-momentum', name: '모멘텀 전략', status: 'available',
    description: '최근 가격 흐름이 강한 종목의 움직임을 활용하는 전략이에요.',
  },
  {
    id: 'f4-value', name: '가치주 전략', status: 'testing',
    description: '기업의 가치에 비해 상대적으로 저평가된 종목을 찾는 전략이에요.',
  },
  {
    id: 'f4-stat-arb', name: '통계적 차익거래 전략', status: 'testing',
    description: '종목 간 가격 관계와 통계적 패턴을 활용하는 전략이에요.',
  },
  {
    id: 'f4-event-driven', name: '이벤트 드리븐 전략', status: 'testing',
    description: '공시나 뉴스 같은 시장 이벤트를 활용해 상대적으로 유리한 종목을 찾는 전략이에요.',
  },
];

export const F4_COLLECTION_INTRO = {
  name: '방탄 F4 전략집',
  description: '시장에서 활용되는 대표적인 투자 전략 4가지를 살펴보세요. 모멘텀 전략은 MVP에서 실제로 이용할 수 있어요.',
};

/**
 * StrategyComingSoon 전용 카피 — 아직 실제 Model/API가 연결되지 않은 전략만 여기 등록한다.
 * TODO(Mock/실제 Model contract 확정 후): canonical strategy id가 정해지면 이 화면 대신 기존
 * StrategyDetail(실 backtest 연동)로 교체한다.
 *
 * 모멘텀은 F4 MVP 대상이 되면서 canonical 백엔드 `momentum` 전략에 실제로 연결됐고(App.tsx의
 * onSelectAvailableStrategy 구현), StrategyDetail로 바로 이동하므로 더 이상 이 placeholder가
 * 필요 없어 항목을 제거했다 — 지금은 물림방지만 실제 연동 전이라 이 placeholder를 쓴다.
 */
export const COMING_SOON_COPY = {
  'loss-avoidance': {
    name: '물림방지 전략',
    meta: 'FE!N 자체 알고리즘',
    description: '큰 손실을 피하면서 안정적인 투자를 지향하는 FE!N의 자체 전략입니다.',
    backLabel: '← 투자전략 목록',
    panelHeading: '백테스트를 준비하고 있어요',
    panelBody: '실제 모델이 연결되면 기간별 성과와 지표를 여기서 확인할 수 있어요.',
    aiBody: '지금은 이 전략의 정보구조만 먼저 볼 수 있어요.',
    ctaHeading: '투자 시작은 아직 준비 중이에요',
    ctaBody: '모델이 연결되면 이 전략으로 투자를 시작할 수 있어요.',
    ctaBadge: '준비 중',
    disclaimer: '※ 이 전략은 아직 실제 모델과 연결되지 않았어요. 위 화면은 정보구조 확인을 위한 준비 화면입니다.',
  },
} as const;
