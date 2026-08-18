import type { KnowledgeArticle, ListResponse, NewsArticle } from '../types';

/* ============================================================
 * InformationExam 외부 API 계약
 *
 *  GET {API_BASE}/news/kr?page=1&size=20
 *  → { items: NewsArticle[], totalCount: number, updatedAt: ISO-8601 }
 *
 *  GET {API_BASE}/knowledge?page=1&size=20
 *  → { items: KnowledgeArticle[], totalCount: number, updatedAt: ISO-8601 }
 * ============================================================ */
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'https://api.example.com/v1/information';

/** true 인 동안 목 데이터를 쓴다. 실 연동 시 false */
export const USE_MOCK = true;

const MOCK_NEWS: ListResponse<NewsArticle> = {
  items: [
    { id: 'n1', title: '코스피, 외국인 순매수에 2,780선 회복', summary: '반도체 대형주를 중심으로 매수세가 유입되며 지수가 사흘 만에 상승 마감했습니다.', thumbnail: null, publisher: '연합뉴스', publishedAt: '2026-08-15T15:42:00+09:00', link: 'https://www.yna.co.kr/' },
    { id: 'n2', title: '한국은행, 기준금리 연 2.50% 동결', summary: '물가 둔화 흐름은 이어지지만 가계부채 부담을 감안해 만장일치로 동결했습니다.', thumbnail: null, publisher: '한국경제', publishedAt: '2026-08-15T11:05:00+09:00', link: 'https://www.hankyung.com/' },
    { id: 'n3', title: '개인 투자자 순매수 상위, 이달에도 배당주 강세', summary: '금리 인하 기대가 이어지며 고배당 종목으로 자금이 몰리는 흐름이 계속되고 있습니다.', thumbnail: null, publisher: '매일경제', publishedAt: '2026-08-15T09:18:00+09:00', link: 'https://www.mk.co.kr/' },
    { id: 'n4', title: '2분기 실적 시즌 마무리, 예상치 상회 기업 62%', summary: '수출 중심 기업의 개선 폭이 컸고, 내수 업종은 종목별 편차가 뚜렷했습니다.', thumbnail: null, publisher: '조선비즈', publishedAt: '2026-08-14T18:30:00+09:00', link: 'https://biz.chosun.com/' },
    { id: 'n5', title: '원/달러 환율 1,320원대 등락, 변동성 축소', summary: '연준의 금리 경로에 대한 시장 전망이 좁혀지면서 환율 변동 폭이 줄었습니다.', thumbnail: null, publisher: 'SBS Biz', publishedAt: '2026-08-14T16:02:00+09:00', link: 'https://biz.sbs.co.kr/' },
  ],
  totalCount: 128, updatedAt: '2026-08-15T15:50:00+09:00',
};

const MOCK_KNOWLEDGE: ListResponse<KnowledgeArticle> = {
  items: [
    { id: 'k1', title: 'PER이 낮으면 정말 싼 주식일까요?', excerpt: '이익 대비 가격을 보는 지표지만, 업종마다 기준이 달라서 같은 숫자도 다르게 읽어야 해요.', category: '지표', readingMinutes: 4, link: 'https://example.com/per' },
    { id: 'k2', title: '변동성이 낮다는 건 어떤 뜻인가요?', excerpt: '수익이 적다는 뜻이 아니라, 오르내리는 폭이 좁다는 뜻이에요. 오래 버티기 쉬워집니다.', category: '리스크', readingMinutes: 3, link: 'https://example.com/volatility' },
    { id: 'k3', title: '최대 낙폭(MDD), 왜 수익률보다 먼저 볼까요?', excerpt: '가장 많이 떨어졌던 순간을 견딜 수 있어야 그 수익률을 실제로 가져갈 수 있어요.', category: '리스크', readingMinutes: 5, link: 'https://example.com/mdd' },
    { id: 'k4', title: '리밸런싱은 얼마나 자주 해야 하나요?', excerpt: '자주 할수록 좋은 건 아니에요. 비용과 세금을 함께 따져야 실익이 남습니다.', category: '전략', readingMinutes: 4, link: 'https://example.com/rebalancing' },
    { id: 'k5', title: '분산투자는 몇 종목부터 효과가 있나요?', excerpt: '종목 수보다 서로 다르게 움직이는지가 중요해요. 같은 업종 20개는 분산이 아닙니다.', category: '전략', readingMinutes: 6, link: 'https://example.com/diversification' },
    { id: 'k6', title: '배당소득세, 미리 알아두면 좋은 것', excerpt: '배당은 받는 순간 세금이 붙어요. 연 2,000만원 기준이 왜 자주 언급되는지 정리했습니다.', category: '세금', readingMinutes: 5, link: 'https://example.com/dividend-tax' },
  ],
  totalCount: 42, updatedAt: '2026-08-15T06:00:00+09:00',
};

/** 8초 타임아웃 + 비정상 응답을 예외로 승격하는 공통 fetch */
async function request<T>(path: string): Promise<ListResponse<T>> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 8000);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: 'application/json' },
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`서버가 ${res.status} 응답을 보냈어요. 잠시 후 다시 시도해주세요.`);
    return (await res.json()) as ListResponse<T>;
  } finally {
    clearTimeout(timer);
  }
}

const delay = <T,>(v: T, ms = 650) => new Promise<T>((r) => setTimeout(() => r(v), ms));

export const fetchNews = (): Promise<ListResponse<NewsArticle>> =>
  USE_MOCK ? delay(MOCK_NEWS) : request<NewsArticle>('/news/kr?page=1&size=20');

export const fetchKnowledge = (): Promise<ListResponse<KnowledgeArticle>> =>
  USE_MOCK ? delay(MOCK_KNOWLEDGE) : request<KnowledgeArticle>('/knowledge?page=1&size=20');
