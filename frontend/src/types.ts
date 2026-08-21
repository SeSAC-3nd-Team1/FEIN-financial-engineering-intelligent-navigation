/** 라우팅 상태 머신의 화면 키 */
export type Screen =
  | 'home' | 'login'
  | 'signup-1' | 'signup-2' | 'signup-3'
  | 'risk' | 'risk-result' | 'investor-check'
  | 'strategy' | 'start'
  | 'information' | 'dashboard' | 'portfolio' | 'stock';

/** 온보딩 Step 01 폼 값 */
export interface SignupPersonal {
  name: string;
  birthdate: string;   // YYMMDD 6자리
  phone: string;       // 숫자만
  /** [선택] AI 기반 맞춤형 서비스 제공을 위한 개인정보 이용 동의 — 회원가입 가능 여부에는 영향 없음 */
  aiPersonalizationConsent: boolean;
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
  why: string;        // AI 편입 사유
}

export interface StockInfo {
  code: string;       // 티커
  price: number;
  cap: string;
  div: string;
  pbr: string;
  per: string;
  roe: string;
  ai: number[];       // AI_AXES 순서의 5축 점수
  desc: string;
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

/* ----- 챗봇 ----- */
export interface ChatMessage {
  id: string;
  role: 'user' | 'bot';
  text: string;
}
