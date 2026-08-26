import { useCallback, useEffect, useRef, useState } from 'react';
import { Info } from 'lucide-react';
import Header from '../components/Header';
import { getBacktestAvailableRange, runBacktest } from '../data/backtestApi';
import { getRecommendedPeriods } from '../data/backtestPeriods';
import {
  ApiError,
  createStrategyRecommendationApi,
  getStrategiesApi,
  type StrategyRecommendationItemResponse,
  type StrategyResponse,
} from '../lib/backendApi';
import { useAuthStore } from '../store/authStore';
import type { BacktestResult, Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  onSelectStrategy: (strategy: StrategyResponse, recommendation: StrategyRecommendationItemResponse) => void;
}

const MATCH_LABEL = {
  BEST: '나와 가장 잘 맞아요',
  GOOD: '비교적 잘 맞아요',
  CAUTION: '조금 더 확인이 필요해요',
} as const;

const RISK_LABEL: Record<string, string> = { LOW: '낮음', MEDIUM: '보통', HIGH: '높음' };
const REBALANCE_LABEL: Record<string, string> = {
  WEEKLY: '주 1회', MONTHLY: '월 1회', QUARTERLY: '분기 1회', YEARLY: '연 1회',
};

interface RecommendationView {
  recommendation: StrategyRecommendationItemResponse;
  strategy: StrategyResponse;
  backtest: BacktestResult | null;
}

interface LoadError {
  code: string;
  message: string;
}

const signedPercent = (value: number) => `${value > 0 ? '+' : ''}${value}%`;
const percent = (value: number) => `${value}%`;

/** 02 결과 — develop의 카드 구조는 유지하고, 표시 값만 실제 추천·전략 카탈로그 응답으로 채운다. */
export default function RiskResult({ userName, onNavigate, onSelectStrategy }: Props) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const assessmentId = useAuthStore((s) => s.investorAssessmentId);
  const investorType = useAuthStore((s) => s.investorType);
  const investorDescription = useAuthStore((s) => s.investorDescription);
  const [hero, setHero] = useState<RecommendationView | null>(null);
  const [alternatives, setAlternatives] = useState<RecommendationView[]>([]);
  const [picked, setPicked] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<LoadError | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  const load = useCallback(async () => {
    if (!accessToken || !assessmentId) {
      setError({ code: 'INVESTOR_PROFILE_NOT_FOUND', message: '저장된 투자성향을 확인할 수 없어요. 투자성향 진단을 다시 진행해주세요.' });
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [recommendation, catalog, availableRange] = await Promise.all([
        createStrategyRecommendationApi(assessmentId, accessToken),
        getStrategiesApi(),
        getBacktestAvailableRange(),
      ]);
      const byId = new Map(catalog.map((item) => [item.id, item]));
      const recentFiveYears = getRecommendedPeriods(availableRange).find((period) => period.id === 'recent-5y');
      if (!recentFiveYears) throw new ApiError('BACKTEST_PERIOD_UNAVAILABLE', '최근 5년 백테스트 기간을 확인할 수 없어요.', 500);
      const catalogItems = [recommendation.primary, ...recommendation.alternatives].map((item) => {
        const strategy = byId.get(item.strategy_id);
        if (!strategy) throw new ApiError('STRATEGY_CATALOG_MISMATCH', '추천 결과와 현재 전략 목록이 일치하지 않아요.', 500);
        return { recommendation: item, strategy };
      });
      // 일부 전략(현재 value)은 실제 백테스트 데이터 준비 전일 수 있다. 해당 전략 하나 때문에
      // 추천 전체를 실패시키거나 목업 수치로 되돌리지 않고, 그 카드의 지표만 '-'로 표시한다.
      const items = await Promise.all(catalogItems.map(async (item) => {
        try {
          return { ...item, backtest: await runBacktest(item.strategy.id, item.strategy.name, recentFiveYears) };
        } catch {
          return { ...item, backtest: null };
        }
      }));
      setHero(items[0]);
      setAlternatives(items.slice(1));
      setPicked(items[0].strategy.id);
    } catch (reason) {
      setError({
        code: reason instanceof ApiError ? reason.code : 'UNKNOWN_ERROR',
        message: reason instanceof Error ? reason.message : '전략 추천을 불러오지 못했어요. 잠시 후 다시 시도해주세요.',
      });
    } finally {
      setLoading(false);
    }
  }, [accessToken, assessmentId]);

  useEffect(() => { void load(); }, [load, retryToken]);

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-16">
          <section className="flex flex-col gap-5 pb-6">
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
                <p className="max-w-[620px] text-base leading-7 text-muted">{error.message}</p>
              </div>
              <div className="flex gap-3">
                <button onClick={() => setRetryToken((value) => value + 1)} className="rounded-field bg-lime px-8 py-4 text-base font-bold text-navy">다시 시도하기</button>
                {error.code === 'AI_PERSONALIZATION_CONSENT_REQUIRED' && (
                  <button onClick={() => onNavigate('strategy-list')} className="rounded-field bg-[#F4F6F1] px-8 py-4 text-base font-bold text-navy">AI 추천 없이 전략 직접 보기</button>
                )}
              </div>
            </section>
          )}

          {!loading && !error && hero && (
            <section className="flex flex-col gap-8">
              <div className="flex flex-col gap-3.5">
                <h2 className="text-[32px] font-bold leading-[46px] tracking-[-0.03em]">이 성향을 바탕으로 전략을 찾아봤어요</h2>
                <p className="text-lg leading-[30px] text-muted">AI가 답변과 전략의 과거 위험 특성을 함께 비교했어요. 추천은 참고용이고, 최종 선택은 {userName}님이 해요.</p>
              </div>

              <button
                onClick={() => setPicked(hero.strategy.id)}
                className={`flex flex-col gap-7 rounded-card bg-surface p-12 text-left ${picked === hero.strategy.id ? 'shadow-[0_0_0_2px_#C6F04D_inset]' : 'shadow-[0_0_0_1px_#E5E9E3_inset]'}`}
              >
                <div className="flex items-start justify-between gap-8">
                  <div className="flex flex-col gap-3.5">
                    <span className="self-start rounded-full bg-lime px-3.5 py-2 text-sm font-bold text-navy">✦ AI가 가장 추천해요</span>
                    <span className="text-lg text-muted">{hero.strategy.description}</span>
                    <span className="text-[38px] font-bold leading-[52px] tracking-[-0.035em]">{hero.strategy.name}</span>
                    <span className="text-[22px] font-bold text-[#3F5222]">{MATCH_LABEL[hero.recommendation.match_level]}</span>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1.5">
                    <span className="text-[15px] text-muted">최근 5년 기준</span>
                    <span className="text-[40px] font-bold tracking-[-0.035em]">{hero.backtest ? signedPercent(hero.backtest.metrics.cagr) : '-'}</span>
                    <span className="text-base text-muted">
                      {hero.backtest ? '연평균 수익률' : '백테스트 준비 중'} · 위험도 {RISK_LABEL[hero.strategy.risk_level] ?? hero.strategy.risk_level}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-8 border-t border-[#F0F2ED] pb-1 pt-7">
                  <Fact label="최대 손실(MDD)" value={hero.backtest ? percent(hero.backtest.metrics.mdd) : '-'} accent />
                  <Fact label="변동성(연)" value={hero.backtest ? percent(hero.backtest.metrics.volatility) : '-'} />
                  <Fact label="샤프 지수" value={hero.backtest?.metrics.sharpe == null ? '-' : String(hero.backtest.metrics.sharpe)} />
                  <Fact label="리밸런싱" value={REBALANCE_LABEL[hero.strategy.rebalance_cycle] ?? hero.strategy.rebalance_cycle} />
                </div>

                <div className="flex gap-5 rounded-[20px] bg-[#F8FCEE] px-9 py-8">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-lime text-lg text-navy">✦</div>
                  <div className="flex flex-col gap-3">
                    <span className="text-[22px] font-bold leading-[34px] tracking-[-0.025em]">왜 {hero.strategy.name}을 추천했나요?</span>
                    <p className="max-w-[720px] text-lg leading-[30px] text-[#3F4A43]">
                      {hero.recommendation.reason} 확인할 점: {hero.recommendation.caution}
                    </p>
                  </div>
                </div>

                <span
                  onClick={(event) => { event.stopPropagation(); onSelectStrategy(hero.strategy, hero.recommendation); }}
                  className="self-start rounded-field bg-lime px-9 py-5 text-lg font-bold text-navy"
                >
                  나에게 맞는 전략 보러가기 →
                </span>
              </button>

              <div className="grid grid-cols-2 gap-5">
                {alternatives.map((item) => (
                  <button
                    key={item.strategy.id}
                    onClick={() => { setPicked(item.strategy.id); onSelectStrategy(item.strategy, item.recommendation); }}
                    className={`flex flex-col gap-4 rounded-card bg-surface p-10 text-left ${picked === item.strategy.id ? 'shadow-[0_0_0_2px_#C6F04D_inset]' : 'shadow-[0_0_0_1px_#E5E9E3_inset]'}`}
                  >
                    <div className="flex flex-col gap-3">
                      <span className="text-[17px] text-muted">{item.strategy.description}</span>
                      <span className="text-[28px] font-bold tracking-[-0.03em]">{item.strategy.name}</span>
                      <span className="text-[19px] font-bold text-[#3F4A43]">{MATCH_LABEL[item.recommendation.match_level]}</span>
                    </div>
                    <div className="flex items-baseline gap-3">
                      <span className="text-[26px] font-bold tracking-[-0.03em]">{item.backtest ? signedPercent(item.backtest.metrics.cagr) : '-'}</span>
                      <span className="text-base text-muted">{item.backtest ? '연평균' : '백테스트 준비 중'} · 위험도 {RISK_LABEL[item.strategy.risk_level] ?? item.strategy.risk_level}</span>
                    </div>
                    <span className="text-base text-muted">
                      MDD {item.backtest ? percent(item.backtest.metrics.mdd) : '-'} · 변동성 {item.backtest ? percent(item.backtest.metrics.volatility) : '-'} · 샤프 {item.backtest?.metrics.sharpe == null ? '-' : item.backtest.metrics.sharpe}
                    </span>
                    <span className="text-[17px] font-semibold text-navy">자세히 보기 →</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          <p className="text-sm leading-[22px] text-subtle">※ 백테스트 수익률은 과거 데이터 기반 예시이며 미래 수익을 보장하지 않습니다. 데이터 준비 중인 전략은 지표를 '-'로 표시합니다.</p>
        </div>
      </main>
    </div>
  );
}

function Fact({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[15px] text-muted">{label}</span>
      <span className={`text-[22px] font-bold ${accent ? 'text-down' : ''}`}>{value}</span>
    </div>
  );
}

/** 투자유형 설명은 hover·tap·키보드 focus 모두에서 확인할 수 있다. */
function InvestorTypeInfo({ type, description }: { type: string; description: string }) {
  const [hoverCapable] = useState(() => typeof window !== 'undefined' && window.matchMedia?.('(hover: hover) and (pointer: fine)').matches);
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
