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
      sourceName: "KB국민은행 KB Think",
      sourceUrl: "https://kbthink.com/dictionary/view.html?dictId=KED-00002075",
      reviewedAt: "2026-08-28",
      contentVersion: "education-v1",
    },
    {
      id: "k2",
      title: "위험과 변동성은 어떻게 이해할까요?",
      excerpt:
        "변동성은 가격이 오르내리는 폭을 살펴보는 방법 중 하나예요. 투자 대상의 위험과 기간을 함께 확인해야 하며, 과거 변동성이 미래 수익을 보장하지는 않습니다.",
      category: "리스크",
      readingMinutes: 3,
      sourceName: "한국경제 용어사전",
      sourceUrl: "https://dic.hankyung.com/economy/view/?seq=9326",
      reviewedAt: "2026-08-28",
      contentVersion: "education-v1",
    },
    {
      id: "k3",
      title: "자산배분으로 손실 위험을 어떻게 나눌까요?",
      excerpt:
        "주식·채권·현금처럼 성격이 다른 자산에 나누어 투자하면 한 자산의 가격 변동이 전체 자산에 미치는 영향을 줄이는 데 도움이 될 수 있어요. 손실이 사라지거나 수익이 보장되는 것은 아닙니다.",
      category: "리스크",
      readingMinutes: 5,
      sourceName: "기획재정부 국채시장",
      sourceUrl: "https://ktb.moef.go.kr/ntndbtEtf.do",
      reviewedAt: "2026-08-28",
      contentVersion: "education-v1",
    },
    {
      id: "k4",
      title: "리밸런싱은 왜 필요한가요?",
      excerpt:
        "자산 가격 변화로 목표 비중이 달라졌을 때 원래의 자산배분으로 되돌리는 방법이에요. 거래 비용과 세금, 투자 목표를 함께 확인해야 합니다.",
      category: "전략",
      readingMinutes: 4,
      sourceName: "한국경제 용어사전",
      sourceUrl: "https://dic.hankyung.com/economy/view/?seq=9120",
      reviewedAt: "2026-08-28",
      contentVersion: "education-v1",
    },
    {
      id: "k5",
      title: "분산투자는 무엇을 나누는 걸까요?",
      excerpt:
        "종목 수를 늘리는 것만으로 충분하지 않아요. 주식·채권·현금 등 자산과 지역·업종처럼 위험 요인이 다른 대상을 함께 살펴야 합니다.",
      category: "전략",
      readingMinutes: 6,
      sourceName: "한국거래소 공개 자료",
      sourceUrl:
        "https://pdf.krx.co.kr/ebook_new/access/ecatalogt.jsp?Dir=23&callmode=normal&catimage=&eclang=ko&start=89&um=s",
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
      sourceName: "국세청",
      sourceUrl:
        "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=7697&mi=2298",
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
