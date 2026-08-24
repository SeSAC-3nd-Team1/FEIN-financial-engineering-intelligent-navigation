/** 라우팅 상태 머신의 화면 키 */
export type Screen =
  | 'home' | 'login'
  | 'signup-1' | 'signup-2' | 'signup-3'
  | 'risk' | 'risk-result' | 'investor-check'
  | 'strategy' | 'start'
  // 투자 시작 Flow — "이 전략으로 시작하기" 이후, 사용자 준비 상태에 따라 필요한 화면으로만 분기
  | 'invest-terms' | 'invest-account' | 'invest-deposit' | 'invest-confirm'
  | 'information' | 'dashboard' | 'portfolio' | 'portfolio-detail' | 'stock' | 'transactions' | 'transaction-detail';

/** 온보딩 Step 01 폼 값 */
export interface SignupPersonal {
  name: string;
  birthdate: string;   // YYMMDD 6자리
  phone: string;       // 숫자만
  /** [선택] AI 기반 맞춤형 서비스 제공을 위한 개인정보 이용 동의 — 회원가입 가능 여부에는 영향 없음 */
  aiPersonalizationConsent: boolean;
  agreements: Agreements;
}

/** 동의 항목 — a1~a4·b·c는 필수(모두 true 여야 인증번호 받기 활성화), ai는 선택(회원가입 가능 여부와 무관) */
export interface Agreements {
  a1: boolean; // 제3자 개인정보 제공 (KT, LGU+, SKT 알뜰폰)
  a2: boolean; // 고유식별정보 처리
  a3: boolean; // 통신사 이용약관
  a4: boolean; // KCB 휴대폰 본인확인 약관
  b: boolean;  // 개인정보 수집·이용 (회원가입/본인인증)
  c: boolean;  // 준회원 이용약관
  ai: boolean; // [선택] AI 기반 맞춤형 서비스 제공을 위한 개인정보 이용 동의
}

/** Step 03 계정 정보 */
export interface Credentials {
  userId: string;
  password: string;
  passwordConfirm: string;
  email: string;
  emailOtp: string;
  emailVerified: boolean;
}

export interface Holding {
  name: string;
  sector: string;
  pct: number;        // 현재 비중 (05)
  target?: number;    // 전략 목표 비중 (04 신규 매수). 없으면 pct 와 동일
  chg: number;        // 오늘 등락률 %
  principal: number;  // 투자 원금(KRW) — 실 계좌가 있으면 PositionResponse.purchase_amount 로 대체된다
  returnRate: number; // 원금 대비 누적 수익률(%) — 실 계좌가 있으면 PositionResponse.return_rate 로 대체된다
  why: string;        // AI 편입 사유
}

/** 재무제표 핵심 지표 — StockDetail "재무제표 핵심 지표" 섹션. 백엔드에 아직 없는 항목이라 목업만 존재한다. */
export interface FinanceRatios {
  debtRatio: number;        // 부채비율 (%)
  currentRatio: number;     // 유동비율 (%)
  quickRatio: number;       // 당좌비율 (%)
  interestCoverage: number; // 이자보상배율 (배)
}

export interface StockInfo {
  code: string;       // 티커
  price: number;
  cap: string;
  div: string;
  pbr: string;
  per: string;
  roe: string;
  ai: number[];        // AI_AXES 순서의 5축 점수 — Portfolio "위험 분석" 탭 전용
  aiEval: number[];    // AI_EVAL_AXES 순서의 6축 점수 — StockDetail "AI 평가" 레이더 전용
  finance: FinanceRatios;
  desc: string;
}

/** 거래 내역 화면에서 쓰는 표시용 모델 — 실 계좌가 있으면 ExecutionResponse(체결내역)를 이 모양으로 매핑해서 쓰고,
 *  계좌가 없거나 체결 기록이 없으면 아래 RECENT_TRANSACTIONS(목업)를 그대로 쓴다. */
export interface TransactionRecord {
  id: string;
  date: string;      // 'YYYY.MM.DD'
  type: '매수' | '매도' | '리밸런싱' | '배당';
  stockName: string;
  amount: number;    // 매수/배당은 양수, 매도/리밸런싱 축소는 음수(KRW)
  note: string;
  quantity: number;  // 체결 수량(소수 주 단위, 소수점 투자 기준) — 배당은 0
  price: number;     // 체결 단가(KRW) — 배당은 0
  fee: number;       // 수수료(KRW) — 실 체결에는 수수료 필드가 없어 0으로 채운다
  status: '체결완료';
}

/** AI 손절/리밸런싱 제안 — 백엔드에 아직 판단 로직이 없어 목업으로만 존재한다 */
export interface AiAlert {
  id: string;
  stockName: string;
  kind: '손절' | '리밸런싱';
  badge: string;     // 종목 배지에 쓰는 짧은 라벨
  headline: string;  // 제안 카드 한 줄 요약
  reason: string;    // "왜 지금인가요?" 모달 본문 — 근거
  action: string;    // 제안하는 구체적 조치
}

export interface TermDef {
  title: string;      // 'PBR (Price Book-value Ratio)'
  ko: string;         // '(주가순자산비율)'
  plain: string;
  formula: string;
}

export type TermKey = 'div' | 'pbr' | 'per' | 'roe';

/* ----- InformationExam 외부 API 응답 계약 ----- */
export interface NewsArticle {
  id: string; title: string; summary: string; thumbnail: string | null;
  publisher: string; publishedAt: string; link: string;
}
export interface KnowledgeArticle {
  id: string; title: string; excerpt: string; category: string;
  readingMinutes: number; link: string;
}
export interface ListResponse<T> { items: T[]; totalCount: number; updatedAt: string; }

export type InfoTab = 'news' | 'knowledge';

/* ----- Backtest 외부 API 응답 계약 ----- */
/** "추천 기간" 프리셋 — 실제 시작·종료일은 데이터팀 확정 전까지 backtestPeriods.ts 에서 mock 으로 관리 */
export interface BacktestPeriod {
  id: string;
  label: string;
  startDate: string; // YYYY-MM-DD
  endDate: string;
  description: string; // 선택 기간 아래 1~2줄 설명
}

export interface BacktestSeriesPoint {
  t: string;         // x축 라벨(날짜)
  strategy: number;  // 기간 시작 대비 누적 수익률 %
  benchmark: number;
}

export interface BacktestMetrics {
  cumulativeReturn: number;
  cagr: number;
  mdd: number;              // 음수 %
  volatility: number;       // 연환산 %
  sharpe: number | null;    // 산출 불가 시 null
}

export interface BacktestResult {
  strategyId: string;
  strategyName: string;
  period: BacktestPeriod;
  series: BacktestSeriesPoint[];
  metrics: BacktestMetrics;
  benchmarkName: string;
  benchmarkMetrics: { cumulativeReturn: number; mdd: number };
}

export interface BacktestAiContext {
  strategyName: string;
  periodType: 'preset' | 'custom';
  periodId: string;
  periodLabel: string;
  periodDescription: string;
  startDate: string;
  endDate: string;
  cumulativeReturn: number;
  cagr: number;
  mdd: number;
  volatility: number;
  sharpe: number | null;
  benchmarkName: string;
  benchmarkReturn: number;
  benchmarkMdd: number;
}

export interface BacktestAiExplanation {
  headline: string;   // 차트 아래 AI 한 줄 해석
  overview: string;   // 상세 설명의 "한눈에 보면"
  caution: string;    // 상세 설명의 "주의해서 볼 점"
  generatedAt: string;
}

/* ----- 챗봇 ----- */
export interface ChatMessage {
  id: string;
  role: 'user' | 'bot';
  text: string;
}
