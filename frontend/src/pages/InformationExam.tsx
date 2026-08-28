import { useCallback, useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";
import Header from "../components/Header";
import { fetchKnowledge, fetchNews } from "../data/informationApi";
import type { InfoTab, KnowledgeArticle, NewsArticle, Screen } from "../types";

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
}

const relTime = (iso: string) => {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const min = Math.floor((Date.now() - t) / 60000);
  if (min < 1) return "방금 전";
  if (min < 60) return `${min}분 전`;
  if (min < 1440) return `${Math.floor(min / 60)}시간 전`;
  const d = new Date(t);
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
};

export default function InformationExam({ userName, onNavigate }: Props) {
  const [tab, setTab] = useState<InfoTab>("news"); // 기본 탭: 한국 뉴스
  const [news, setNews] = useState<NewsArticle[] | null>(null);
  const [knowledge, setKnowledge] = useState<KnowledgeArticle[] | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** 탭 데이터 로드. 캐시가 있으면 재요청하지 않는다 (force=true 면 강제) */
  const load = useCallback(
    async (target: InfoTab, force = false) => {
      const cached = target === "news" ? news : knowledge;
      if (cached && !force) return;
      setLoading(true);
      setError(null);
      try {
        if (target === "news") {
          const res = await fetchNews();
          setNews(res.items);
          setUpdatedAt(res.updatedAt);
        } else {
          const res = await fetchKnowledge();
          setKnowledge(res.items);
          setUpdatedAt(res.updatedAt);
        }
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : "네트워크 연결을 확인한 뒤 다시 시도해주세요.",
        );
      } finally {
        setLoading(false);
      }
    },
    [news, knowledge],
  );

  useEffect(() => {
    void load(tab);
  }, [tab, load]);

  const items = tab === "news" ? news : knowledge;
  const ready = !loading && !error && items !== null;
  const empty = ready && items!.length === 0;

  return (
    <div className="min-h-screen bg-canvas">
      <Header
        active="information"
        userName={userName}
        onNavigate={onNavigate}
      />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">정보</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
              오늘 시장에서
              <br />
              알아두면 좋은 것들
            </h1>
            <p className="max-w-[820px] text-[19px] leading-8 text-muted">
              실시간 뉴스와 공식 자료를 바탕으로 검수한 금융 교육 콘텐츠를
              구분해 보여드려요.
            </p>
          </section>

          <div className="flex items-center justify-between gap-6">
            <div className="flex items-center gap-2 rounded-full bg-[#F4F6F1] p-1.5">
              <TabBtn active={tab === "news"} onClick={() => setTab("news")}>
                한국 뉴스
              </TabBtn>
              <TabBtn
                active={tab === "knowledge"}
                onClick={() => setTab("knowledge")}
              >
                금융 상식
              </TabBtn>
            </div>
            <div className="flex items-center gap-4">
              {updatedAt && (
                <span className="text-[15px] text-subtle">
                  {relTime(updatedAt)} 업데이트
                </span>
              )}
              <button
                onClick={() => void load(tab, true)}
                className="flex items-center gap-2 rounded-[10px] bg-surface px-5 py-3 text-[15px] font-semibold text-[#3F4A43] shadow-[0_0_0_1px_#E5E9E3_inset]"
              >
                <RotateCcw size={15} /> 새로고침
              </button>
            </div>
          </div>

          {loading && (
            <div className="flex flex-col gap-3">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="flex animate-pulse gap-6 rounded-[20px] bg-surface px-8 py-7"
                >
                  <div className="flex flex-1 flex-col gap-3 pt-1.5">
                    <div className="h-[22px] w-[70%] rounded-md bg-[#F0F2ED]" />
                    <div className="h-4 w-[92%] rounded-md bg-[#F4F6F1]" />
                    <div className="h-3.5 w-[34%] rounded-md bg-[#F4F6F1]" />
                  </div>
                </div>
              ))}
            </div>
          )}

          {error && (
            <div className="flex flex-col items-center gap-5 rounded-card bg-surface px-10 py-20">
              <div className="flex h-14 w-14 items-center justify-center rounded-[18px] bg-[#FDECEC] text-2xl font-bold text-[#D64545]">
                !
              </div>
              <h2 className="text-2xl font-bold tracking-[-0.025em]">
                지금은 정보를 불러올 수 없어요
              </h2>
              <p className="max-w-[520px] text-center text-[17px] leading-7 text-muted">
                {error}
              </p>
              <button
                onClick={() => void load(tab, true)}
                className="rounded-field bg-lime px-8 py-4 text-[17px] font-bold text-navy"
              >
                다시 시도하기
              </button>
            </div>
          )}

          {empty && (
            <div className="flex flex-col items-center gap-4 rounded-card bg-surface px-10 py-20">
              <h2 className="text-2xl font-bold tracking-[-0.025em]">
                아직 보여드릴 글이 없어요
              </h2>
              <p className="text-[17px] leading-7 text-muted">
                잠시 뒤에 새로운 소식이 채워질 거예요.
              </p>
            </div>
          )}

          {ready && tab === "news" && news!.length > 0 && (
            <div className="flex flex-col gap-3">
              {news!.map((a) => (
                <a
                  key={a.id}
                  href={a.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-6 rounded-[20px] bg-surface px-8 py-7 shadow-[0_0_0_1px_#FFFFFF_inset] hover:shadow-[0_0_0_1.5px_#C6F04D_inset]"
                >
                  <div className="flex min-w-0 flex-1 flex-col gap-2.5">
                    <span className="text-[21px] font-bold leading-8 tracking-[-0.02em] [text-wrap:pretty]">
                      {a.title}
                    </span>
                    <span className="text-base leading-[26px] text-muted">
                      {a.summary}
                    </span>
                    <div className="flex items-center gap-2.5 pt-0.5 text-[15px] text-subtle">
                      <span className="font-semibold text-[#3F4A43]">
                        {a.publisher}
                      </span>
                      <span>·</span>
                      <span>{relTime(a.publishedAt)}</span>
                    </div>
                  </div>
                  <span className="self-center text-lg text-[#A6AFA7]">↗</span>
                </a>
              ))}
            </div>
          )}

          {ready && tab === "knowledge" && knowledge!.length > 0 && (
            <div className="grid grid-cols-2 gap-4">
              {knowledge!.map((k) => (
                <a
                  key={k.id}
                  href={k.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex flex-col gap-3.5 rounded-[20px] bg-surface p-9 shadow-[0_0_0_1px_#FFFFFF_inset] hover:shadow-[0_0_0_1.5px_#C6F04D_inset]"
                >
                  <div className="flex items-center gap-2.5">
                    <span className="rounded-full bg-[#F1FBD4] px-3 py-1.5 text-sm font-bold text-[#3F5222]">
                      {k.category}
                    </span>
                    <span className="text-sm text-subtle">
                      {k.readingMinutes}분 읽기
                    </span>
                  </div>
                  <span className="text-[22px] font-bold leading-[34px] tracking-[-0.025em] [text-wrap:pretty]">
                    {k.title}
                  </span>
                  <span className="flex-1 text-base leading-[27px] text-muted">
                    {k.excerpt}
                  </span>
                  <span className="text-sm leading-6 text-subtle">
                    출처: {k.sourceName} · 검수일: {k.reviewedAt} ·{" "}
                    {k.contentVersion}
                  </span>
                  <span className="text-base font-semibold text-navy">
                    공식 자료 확인 →
                  </span>
                </a>
              ))}
            </div>
          )}

          {tab === "knowledge" ? (
            <p className="text-sm leading-[22px] text-subtle">
              ※ 금융 상식은 교육 목적의 정적 콘텐츠이며, 공식 자료를 기준으로
              검수했습니다. 세율·제도·상품 조건은 변경될 수 있으므로 최신 내용은
              출처 기관에서 확인하세요. 투자 권유나 수익 보장이 아니며, 개인의
              투자·세무 판단에 대한 책임을 대신하지 않습니다.
            </p>
          ) : (
            <p className="text-sm leading-[22px] text-subtle">
              ※ 외부 매체가 제공하는 정보이며, 특정 종목의 매매를 권유하지
              않습니다.
            </p>
          )}
        </div>
      </main>
    </div>
  );
}

function TabBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-7 py-3.5 text-[17px] font-semibold ${
        active
          ? "bg-surface text-ink shadow-[0_2px_8px_rgba(24,36,58,0.08)]"
          : "text-muted"
      }`}
    >
      {children}
    </button>
  );
}
