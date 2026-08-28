import type { KnowledgeArticle, ListResponse, NewsArticle } from "../types";

/* ============================================================
 * InformationExam 외부 API 계약
 *
 *  GET {API_BASE}/news/kr?page=1&size=20
 *  → { items: NewsArticle[], totalCount: number, updatedAt: ISO-8601 }
 *
 *  금융 상식은 시세·세제 계산이 아닌 정적 교육 콘텐츠로 운영한다.
 *  각 항목은 공식 기관 자료를 출처로 표시하며, 변경 빈도가 높은 수치·정책은 하드코딩하지 않는다.
 * ============================================================ */
export const API_BASE = "/api/v1/information";

export const KNOWLEDGE_CONTENT: ListResponse<KnowledgeArticle> = {
  items: [
    {
      id: "k1",
      title: "PER이 낮으면 정말 싼 주식일까요?",
      excerpt:
        "이익 대비 가격을 보는 지표지만, 업종·성장성·부채를 함께 살펴야 같은 숫자를 올바르게 비교할 수 있어요.",
      category: "지표",
      readingMinutes: 4,
      sourceName: "한국거래소",
      sourceUrl:
        "https://global.krx.co.kr/contents/GLB/02/0203/0203010000/GLB0203010000.jsp",
      reviewedAt: "2026-08-28",
      contentVersion: "education-v1",
    },
    {
      id: "k2",
      title: "변동성이 낮다는 건 어떤 뜻인가요?",
      excerpt:
        "수익이 적다는 뜻이 아니라 가격이 오르내리는 폭이 상대적으로 좁다는 뜻이에요. 과거 변동성이 미래 수익을 보장하지는 않습니다.",
      category: "리스크",
      readingMinutes: 3,
      sourceName: "금융감독원",
      sourceUrl: "https://www.fss.or.kr/fss/consumer/consumer020101.do",
      reviewedAt: "2026-08-28",
      contentVersion: "education-v1",
    },
    {
      id: "k3",
      title: "최대 낙폭(MDD), 왜 수익률과 함께 볼까요?",
      excerpt:
        "과거 관측 기간 중 고점에서 저점까지의 하락 폭을 보는 지표예요. 과거 MDD가 미래 손실 한도를 의미하지는 않습니다.",
      category: "리스크",
      readingMinutes: 5,
      sourceName: "한국거래소",
      sourceUrl:
        "https://global.krx.co.kr/contents/GLB/02/0203/0203010000/GLB0203010000.jsp",
      reviewedAt: "2026-08-28",
      contentVersion: "education-v1",
    },
    {
      id: "k4",
      title: "리밸런싱은 얼마나 자주 해야 하나요?",
      excerpt:
        "정해진 정답은 없어요. 거래 비용·세금·운용 목표와 자산 비중의 이탈 정도를 함께 확인해야 합니다.",
      category: "전략",
      readingMinutes: 4,
      sourceName: "금융감독원",
      sourceUrl: "https://www.fss.or.kr/fss/consumer/consumer020101.do",
      reviewedAt: "2026-08-28",
      contentVersion: "education-v1",
    },
    {
      id: "k5",
      title: "분산투자는 무엇을 나누는 걸까요?",
      excerpt:
        "종목 수를 늘리는 것만으로 충분하지 않아요. 자산·지역·업종처럼 위험 요인이 다른 대상을 함께 살펴야 합니다.",
      category: "전략",
      readingMinutes: 6,
      sourceName: "한국거래소",
      sourceUrl:
        "https://global.krx.co.kr/contents/GLB/02/0203/0203010000/GLB0203010000.jsp",
      reviewedAt: "2026-08-28",
      contentVersion: "education-v1",
    },
    {
      id: "k6",
      title: "배당과 세금은 어디서 확인하나요?",
      excerpt:
        "배당 관련 세율·공제·신고 기준은 상품과 납세자 상황, 법령 개정에 따라 달라질 수 있어요. 최신 기준은 공식 세무 안내를 확인하세요.",
      category: "세금",
      readingMinutes: 5,
      sourceName: "국가법령정보센터",
      sourceUrl: "https://www.law.go.kr/법령/소득세법",
      reviewedAt: "2026-08-28",
      contentVersion: "education-v1",
    },
  ],
  totalCount: 6,
  updatedAt: "2026-08-28T00:00:00Z",
};

/** 8초 타임아웃 + 비정상 응답을 예외로 승격하는 공통 fetch */
async function request<T>(path: string): Promise<ListResponse<T>> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 8000);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: "application/json" },
      signal: ctrl.signal,
    });
    if (!res.ok)
      throw new Error(
        `서버가 ${res.status} 응답을 보냈어요. 잠시 후 다시 시도해주세요.`,
      );
    return (await res.json()) as ListResponse<T>;
  } finally {
    clearTimeout(timer);
  }
}

export const fetchNews = (): Promise<ListResponse<NewsArticle>> =>
  request<NewsArticle>("/news/kr?page=1&size=20");

export const fetchKnowledge = (): Promise<ListResponse<KnowledgeArticle>> =>
  Promise.resolve(KNOWLEDGE_CONTENT);
