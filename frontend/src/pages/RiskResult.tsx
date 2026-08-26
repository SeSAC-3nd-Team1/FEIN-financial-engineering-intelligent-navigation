import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Info } from 'lucide-react';
import Header from '../components/Header';
import {
  createStrategyRecommendationApi,
  getStrategiesApi,
  type StrategyRecommendationItemResponse,
  type StrategyRecommendationResponse,
  type StrategyResponse,
} from '../lib/backendApi';
import { useAuthStore } from '../store/authStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  onSelectStrategy: (id: string) => void;
}

const MATCH_LABEL = {
  BEST: '나와 가장 잘 맞아요',
  GOOD: '비교적 잘 맞아요',
  CAUTION: '주의사항을 확인해주세요',
} as const;

const RISK_LABEL: Record<string, string> = { LOW: '낮음', MEDIUM: '보통', HIGH: '높음' };
const REBALANCE_LABEL: Record<string, string> = {
  WEEKLY: '주 1회', MONTHLY: '월 1회', QUARTERLY: '분기 1회', YEARLY: '연 1회',
};

interface RecommendationView {
  recommendation: StrategyRecommendationItemResponse;
  strategy: StrategyResponse;
}

/** 실제 투자성향 assessment와 전략 카탈로그를 AI 추천 API에 연결해 순위·근거·주의사항을 표시한다. */
export default function RiskResult({ userName, onNavigate, onSelectStrategy }: Props) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const assessmentId = useAuthStore((s) => s.investorAssessmentId);
  const investorType = useAuthStore((s) => s.investorType);
  const investorDescription = useAuthStore((s) => s.investorDescription);
  const [recommendation, setRecommendation] = useState<StrategyRecommendationResponse | null>(null);
  const [catalog, setCatalog] = useState<StrategyResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  const load = useCallback(async () => {
    if (!accessToken || !assessmentId) {
      setError('저장된 투자성향을 확인할 수 없어요. 투자성향 진단을 다시 진행해주세요.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [nextRecommendation, nextCatalog] = await Promise.all([
        createStrategyRecommendationApi(assessmentId, accessToken),
        getStrategiesApi(),
      ]);
      const catalogIds = new Set(nextCatalog.map((item) => item.id));
      const recommendationIds = [
        nextRecommendation.primary.strategy_id,
        ...nextRecommendation.alternatives.map((item) => item.strategy_id),
      ];
      if (recommendationIds.some((id) => !catalogIds.has(id))) {
        throw new Error('추천 결과와 현재 전략 목록이 일치하지 않아요. 잠시 후 다시 시도해주세요.');
      }
      setRecommendation(nextRecommendation);
      setCatalog(nextCatalog);
      setSelectedId(nextRecommendation.primary.strategy_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '전략 추천을 불러오지 못했어요. 잠시 후 다시 시도해주세요.');
    } finally {
      setLoading(false);
    }
  }, [accessToken, assessmentId]);

  useEffect(() => { void load(); }, [load, retryToken]);

  const views = useMemo(() => {
    if (!recommendation) return [];
    const byId = new Map(catalog.map((item) => [item.id, item]));
    return [recommendation.primary, ...recommendation.alternatives]
      .map((item) => ({ recommendation: item, strategy: byId.get(item.strategy_id) }))
      .filter((item): item is RecommendationView => Boolean(item.strategy));
  }, [catalog, recommendation]);

  const selected = views.find((item) => item.strategy.id === selectedId) ?? views[0] ?? null;

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-12">
          <section className="flex flex-col gap-5 pb-2">
            <span className="text-base font-semibold text-muted">투자자 정보 확인 · 완료</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">투자성향을 확인했어요</h1>
            {investorType && investorDescription ? (
              <div className="flex items-center gap-2.5">
                <span className="rounded-full bg-lime px-5 py-2.5 text-[22px] font-bold text-navy">{investorType}이에요</span>
                <InvestorTypeInfo type={investorType} description={investorDescription} />
              </div>
            ) : (
              <p className="text-lg text-muted">저장된 투자성향 정보가 없어요.</p>
            )}
          </section>

          {loading && (
            <section aria-live="polite" className="flex flex-col items-center gap-3 rounded-card bg-surface px-10 py-20">
              <span className="text-[24px] font-bold">실제 전략 데이터를 비교하고 있어요</span>
              <p className="text-base text-muted">저장된 투자성향과 현재 이용 가능한 전략을 분석합니다.</p>
            </section>
          )}

          {!loading && error && (
            <section role="alert" className="flex flex-col items-center gap-5 rounded-card bg-surface px-10 py-16 text-center">
              <div className="flex flex-col gap-2">
                <span className="text-[24px] font-bold">전략 추천을 불러오지 못했어요</span>
                <p className="max-w-[620px] text-base leading-7 text-muted">{error}</p>
              </div>
              <button onClick={() => setRetryToken((value) => value + 1)} className="rounded-field bg-lime px-8 py-4 text-base font-bold text-navy">
                다시 시도하기
              </button>
            </section>
          )}

          {!loading && !error && selected && recommendation && (
            <section className="flex flex-col gap-8">
              <div className="flex flex-col gap-3.5">
                <h2 className="text-[32px] font-bold leading-[46px] tracking-[-0.03em]">이 성향을 바탕으로 전략을 비교했어요</h2>
                <p className="text-lg leading-[30px] text-muted">
                  적합도는 예상수익률이 아니라 투자성향과 전략 특성의 일치 정도예요. 최종 선택은 {userName}님이 해요.
                </p>
              </div>

              <div className="grid grid-cols-3 gap-4">
                {views.map(({ recommendation: item, strategy }) => (
                  <button
                    key={strategy.id}
                    onClick={() => setSelectedId(strategy.id)}
                    className={`flex flex-col gap-3 rounded-[20px] p-7 text-left ${
                      selected.strategy.id === strategy.id
                        ? 'bg-[#F8FCEE] shadow-[0_0_0_2px_#C6F04D_inset]'
                        : 'bg-surface shadow-[0_0_0_1px_#E5E9E3_inset]'
                    }`}
                  >
                    <span className="text-sm font-semibold text-muted">추천 {item.rank}순위</span>
                    <span className="text-[22px] font-bold tracking-[-0.02em]">{strategy.name}</span>
                    <span className="text-base font-bold text-[#3F5222]">{MATCH_LABEL[item.match_level]}</span>
                  </button>
                ))}
              </div>

              <article className="flex flex-col gap-7 rounded-card bg-surface p-12 shadow-[0_0_0_1px_#E5E9E3_inset]">
                <div className="flex items-start justify-between gap-8">
                  <div className="flex flex-col gap-3">
                    {selected.recommendation.rank === 1 && (
                      <span className="self-start rounded-full bg-lime px-3.5 py-2 text-sm font-bold text-navy">✦ AI가 가장 추천해요</span>
                    )}
                    <h3 className="text-[38px] font-bold leading-[52px] tracking-[-0.035em]">{selected.strategy.name}</h3>
                    <p className="max-w-[650px] text-lg leading-[30px] text-muted">{selected.strategy.description}</p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span className="text-[15px] text-muted">투자성향 적합도</span>
                    <span className="text-[40px] font-bold tracking-[-0.035em]">{Math.round(selected.recommendation.score * 100)}%</span>
                    <span className="text-sm text-subtle">수익률·성공확률 아님</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-5 border-t border-[#F0F2ED] pt-7">
                  <Fact label="위험도" value={RISK_LABEL[selected.strategy.risk_level] ?? selected.strategy.risk_level} />
                  <Fact label="리밸런싱" value={REBALANCE_LABEL[selected.strategy.rebalance_cycle] ?? selected.strategy.rebalance_cycle} />
                </div>

                <div className="grid grid-cols-2 gap-5">
                  <div className="flex flex-col gap-2 rounded-[18px] bg-[#F8FCEE] px-8 py-7">
                    <span className="text-[17px] font-bold">추천 이유</span>
                    <p className="text-base leading-7 text-[#3F4A43]">{selected.recommendation.reason}</p>
                  </div>
                  <div className="flex flex-col gap-2 rounded-[18px] bg-[#FFF6EC] px-8 py-7">
                    <span className="text-[17px] font-bold text-[#7A5A1E]">확인할 점</span>
                    <p className="text-base leading-7 text-[#7A5A1E]">{selected.recommendation.caution}</p>
                  </div>
                </div>

                <button
                  onClick={() => onSelectStrategy(selected.strategy.id)}
                  className="self-start rounded-field bg-lime px-9 py-5 text-lg font-bold text-navy"
                >
                  이 전략 자세히 보기 →
                </button>
              </article>

              <p className="text-sm leading-[22px] text-subtle">
                추천 버전 {recommendation.recommendation_version} · 모델 {recommendation.model_version} · 데이터셋 {recommendation.dataset_version}
              </p>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[15px] text-muted">{label}</span>
      <span className="text-[22px] font-bold">{value}</span>
    </div>
  );
}

/** 투자유형 설명은 hover·tap·키보드 focus 모두에서 확인할 수 있다. */
function InvestorTypeInfo({ type, description }: { type: string; description: string }) {
  const [hoverCapable] = useState(
    () => typeof window !== 'undefined' && window.matchMedia?.('(hover: hover) and (pointer: fine)').matches,
  );
  const [open, setOpen] = useState(false);
  const pointerActivated = useRef(false);
  const markPointer = () => { pointerActivated.current = true; };

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label={`${type} 설명 보기`}
        aria-expanded={open}
        onMouseDown={markPointer}
        onTouchStart={markPointer}
        onMouseEnter={() => hoverCapable && setOpen(true)}
        onMouseLeave={() => hoverCapable && setOpen(false)}
        onFocus={() => {
          if (pointerActivated.current) { pointerActivated.current = false; return; }
          setOpen(true);
        }}
        onBlur={() => setOpen(false)}
        onClick={() => {
          if (hoverCapable) { setOpen(true); return; }
          setOpen((value) => !value);
        }}
        className="flex h-8 w-8 items-center justify-center rounded-full text-subtle hover:text-navy"
      >
        <Info size={22} />
      </button>
      {open && (
        <div role="tooltip" className="absolute left-0 top-full z-10 mt-2 w-[280px] rounded-[14px] bg-navy px-5 py-4 text-[15px] leading-6 text-white shadow-[0_8px_24px_rgba(24,36,58,0.25)]">
          {description}
        </div>
      )}
    </span>
  );
}
