import type { KnowledgeArticle, ListResponse, NewsArticle } from '../types';

/* ============================================================
 * InformationExam 외부 API 계약
 *
 *  GET {API_BASE}/news/kr?page=1&size=20
 *  → { items: NewsArticle[], totalCount: number, updatedAt: ISO-8601 }
 *
 *  금융 상식은 이번 연동 범위 밖이므로 기존 mock을 유지한다.
 * ============================================================ */
export const API_BASE = '/api/v1/information';

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
  request<NewsArticle>('/news/kr?page=1&size=20');

export const fetchKnowledge = (): Promise<ListResponse<KnowledgeArticle>> =>
  delay(MOCK_KNOWLEDGE);
