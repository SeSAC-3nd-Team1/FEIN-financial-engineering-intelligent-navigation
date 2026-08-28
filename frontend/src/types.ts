/** 라우팅 상태 머신의 화면 키 */
export type Screen =
  | "home"
  | "login"
  // 'start-signup': Home "시작하기" 전용 진입 화면 — 이메일을 먼저 받아 SignupStep1으로 prefill해
  // 넘겨준다(Netflix식 이메일 선입력 패턴). 신규 email verification API/스키마는 추가하지 않고,
  // 기존 SignupPersonal.email 값만 미리 채워서 기존 회원가입 Flow(signup-1~3)로 그대로 이어간다.
  | "start-signup"
  | "signup-1"
  | "signup-2"
  | "signup-3"
  | "risk"
  | "risk-result"
  | "investor-check"
  | "strategy-list"
  | "strategy"
  | "start"
  // 물·방·개 전략 체계(UI/IA 개편) — strategy-list 카드에서만 진입. 모멘텀은 실제 canonical
  // 전략에 연결돼 있어 'strategy' 화면(StrategyDetail)을 그대로 쓰고, 물림방지만 아직 실 Model/API
  // 미연결이라 별도 placeholder 화면(strategy-coming-soon-loss-avoidance)이 필요하다.
  | "strategy-f4"
  | "strategy-coming-soon-loss-avoidance"
  | "strategy-preview"
  // 투자 시작 Flow — "이 전략으로 시작하기" 이후, 사용자 준비 상태에 따라 필요한 화면으로만 분기
  | "invest-terms"
  | "invest-account"
  | "invest-deposit"
  | "invest-confirm"
  // 계좌 준비 Flow — 전략 선택과 무관하게 계좌를 만들고 현금만 입금할 수 있다.
  | "account-setup"
  | "account-deposit"
  | "information"
  | "dashboard"
  | "portfolio"
  | "portfolio-detail"
  | "stock"
  | "transactions"
  | "transaction-detail"
  | "rebalance-alerts"
  | "all-holdings"
  // 자금관리: 추가 투자/출금 모두 금액 입력 → 확인 → 실행 대기(*-pending, FundManagementComingSoon
  // 재사용) 3단계 실 UI Flow. Backend contract가 아직 없어 실제 매수/매도/출금 실행만 placeholder로 남긴다.
  | "fund-add"
  | "fund-add-confirm"
  | "fund-add-pending"
  | "fund-withdraw"
  | "fund-withdraw-confirm"
  | "fund-withdraw-pending";

/** 온보딩 Step 01 폼 값 — 이메일 인증만 쓰는 정책으로, email도 여기서 함께 입력받는다(인증 자체는 Step 02) */
export interface SignupPersonal {
  name: string;
  birthdate: string; // YYMMDD 6자리
  email: string;
  agreements: Agreements;
}

/** 동의 항목 — 셋 다 필수(모두 true 여야 이메일 인증 진행 가능).
 *  휴대폰 SMS/KCB/통신사 본인확인 관련 동의(구 a1~a4)는 더 이상 회원가입에서 요구하지 않아 제거했다.
 *  AI 기반 맞춤형 서비스 이용 동의(AI_PERSONALIZATION)는 투자성향 분석/챗봇 개인화 응답 제공 여부를
 *  가르는 실제 권한 경계로 쓰이고 있어(recommendation.py의 has_ai_personalization_consent), 선택이
 *  아니라 필수 동의로 관리한다 — 서버 약관 카탈로그에서도 is_required=true다. */
export interface Agreements {
  b: boolean; // 개인정보 수집·이용 동의
  c: boolean; // 서비스 이용약관 동의
  ai: boolean; // AI 기반 맞춤형 서비스 이용 동의
}

/** Step 03 계정 정보 — email은 Step 01/02에서 이미 입력·인증 완료된 상태라 여기서는 다루지 않는다 */
export interface Credentials {
  userId: string;
  password: string;
  passwordConfirm: string;
  phone: string;
}

export interface Holding {
  name: string;
  sector: string;
  pct: number; // 현재 비중 (05)
  target?: number; // 전략 목표 비중 (04 신규 매수). 없으면 pct 와 동일
  chg: number | null; // 오늘 등락률 %. 제공되지 않으면 null
  // 투자 원금/누적 수익률 — buildPortfolioHoldings() 로 만든 실 계좌 보유 종목엔 없고(PositionResponse 에서 직접 읽는다),
  // PortfolioDetail/AllHoldings/RebalanceAlerts 처럼 종목별로 원금·수익률을 표로 보여주는 화면의 로컬 홀딩 모델만 채운다.
  principal?: number; // 투자 원금(KRW) — 실 계좌가 있으면 PositionResponse.purchase_amount 로 대체된다
  returnRate?: number; // 원금 대비 누적 수익률(%) — 실 계좌가 있으면 PositionResponse.return_rate 로 대체된다
  why: string; // AI 편입 사유
}

export interface StockInfo {
  code: string; // 티커
  price: number;
  cap: string;
  div: string;
  pbr: string;
  per: string;
  roe: string;
  ai: number[];
  desc: string;
}

/** 거래 내역 화면에서 쓰는 표시용 모델 — 실 계좌가 있으면 ExecutionResponse(체결내역)를 이 모양으로 매핑해서 쓰고,
 *  계좌가 없거나 체결 기록이 없으면 아래 RECENT_TRANSACTIONS(목업)를 그대로 쓴다. */
export interface TransactionRecord {
  id: string;
  date: string; // 'YYYY.MM.DD'
  type: "매수" | "매도" | "리밸런싱" | "배당";
  stockName: string;
  amount: number; // 매수/배당은 양수, 매도/리밸런싱 축소는 음수(KRW)
  note: string;
  quantity: number; // 체결 수량(소수 주 단위, 소수점 투자 기준) — 배당은 0
  price: number; // 체결 단가(KRW) — 배당은 0
  fee: number; // 수수료(KRW) — 실 체결에는 수수료 필드가 없어 0으로 채운다
  status: "체결완료";
}

/** AI 손절/리밸런싱 제안 — 실 계좌가 있으면 lib/rebalancing.ts가 PortfolioResponse.rebalancing_proposals(실
 *  데이터, 규칙기반)로부터 이 모양을 만들어 채운다. 그 실데이터 경로는 항상 kind: '리밸런싱'만 쓴다 — 손절 판단은
 *  아직 모델이 없어 서술형 reason과 함께 리밸런싱 모델이 붙기 전까지는 만들 수 없다(그때까지는 목업만 '손절'을 쓴다). */
export interface AiAlert {
  id: string;
  stockName: string;
  kind: "손절" | "리밸런싱";
  badge: string; // 종목 배지에 쓰는 짧은 라벨
  headline: string; // 제안 카드 한 줄 요약
  reason: string; // "왜 지금인가요?" 모달 본문 — 근거
  action: string; // 제안하는 구체적 조치
  /** 실 데이터일 때만 채워진다 — 있으면 "조정 전/후" 시트가 이 값을 그대로 쓰고,
   *  없으면(목업) 화면이 보유 종목 목록에서 같은 이름을 찾아 대신 파생시킨다. */
  currentWeight?: number;
  targetWeight?: number;
  recommendedAmount?: number;
}

export interface TermDef {
  title: string; // 'PBR (Price Book-value Ratio)'
  ko: string; // '(주가순자산비율)'
  plain: string;
  formula: string;
}

export type TermKey = "div" | "pbr" | "per" | "roe";

/* ----- InformationExam 외부 API 응답 계약 ----- */
export interface NewsArticle {
  // 연동된 뉴스 API(/news/kr)가 이미지를 내려주지 않아 thumbnail 필드는 쓰지 않는다.
  id: string;
  title: string;
  summary: string;
  publisher: string;
  publishedAt: string;
  link: string;
}
export interface KnowledgeArticle {
  id: string;
  title: string;
  excerpt: string;
  category: string;
  readingMinutes: number;
  link: string;
  sourceName: string;
  sourceUrl: string;
  reviewedAt: string;
  contentVersion: string;
}
export interface ListResponse<T> {
  items: T[];
  totalCount: number;
  updatedAt: string;
}

export type InfoTab = "news" | "knowledge";

/* ----- Backtest 외부 API 응답 계약 ----- */
/** Backend 실제 KRX 백테스트에 전달하는 조회 기간. */
export interface BacktestPeriod {
  id: string;
  label: string;
  startDate: string; // YYYY-MM-DD
  endDate: string;
  description: string; // 선택 기간 아래 1~2줄 설명
}

export interface BacktestSeriesPoint {
  t: string; // x축 라벨(날짜)
  strategy: number; // 기간 시작 대비 누적 수익률 %
  benchmark: number;
}

export interface BacktestMetrics {
  cumulativeReturn: number;
  cagr: number;
  mdd: number; // 음수 %
  volatility: number; // 연환산 %
  sharpe: number | null; // 산출 불가 시 null
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
  periodType: "preset" | "custom";
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
  headline: string; // 차트 아래 AI 한 줄 해석
  overview: string; // 상세 설명의 "한눈에 보면"
  caution: string; // 상세 설명의 "주의해서 볼 점"
  generatedAt: string;
}

/* ----- 챗봇 ----- */
export interface ChatMessage {
  id: string;
  role: "user" | "bot";
  text: string;
  status?: "COMPLETED" | "NEEDS_CLARIFICATION" | "REFUSED";
  caution?: string | null;
  suggestedQuestions?: string[];
}
