import { useMemo, useState } from 'react';
import { Check, X } from 'lucide-react';
import Header from '../components/Header';
import { AI_ALERTS, ALL_HOLDINGS as MOCK_HOLDINGS, HOLD_TOTAL as MOCK_HOLD_TOTAL, STOCK_INFO } from '../data/holdings';
import { STRATEGIES } from '../data/strategies';
import { useTradingData } from '../hooks/useTradingData';
import { won } from '../lib/validation';
import { useTradingStore } from '../store/tradingStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  strategyId: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
}

/** AI 제안 종류별 배지 색 — PortfolioDetail 의 요약 카드와 동일한 배색을 공유한다 */
const ALERT_BADGE: Record<'손절' | '리밸런싱', string> = {
  '손절': 'bg-[#FBEAEA] text-up',
  '리밸런싱': 'bg-[#FCF3E4] text-warn',
};

/** `/rebalance-alerts` — AI 손절·리밸런싱 제안 전체 목록. PortfolioDetail "AI의 리밸런싱 제안"의 "더보기"에서 진입한다.
 *  백엔드에 아직 판단 로직이 없어 AI_ALERTS(목업)를 그대로 쓰고, 조정 비중 계산에만 실 계좌 보유 종목을 우선 사용한다. */
export default function RebalanceAlerts({ userName, strategyId, onNavigate, onBack }: Props) {
  useTradingData();
  const portfolio = useTradingStore((state) => state.portfolio);
  const selectedStrategy = STRATEGIES.find((s) => s.id === strategyId) ?? STRATEGIES[0];

  // 실 계좌가 있으면 포지션을, 없으면 목업 20종목을 쓴다 — PortfolioDetail 과 동일한 대체 규칙.
  const HOLD_TOTAL = portfolio ? Number(portfolio.total_assets) : MOCK_HOLD_TOTAL;
  const ALL_HOLDINGS = useMemo(() => {
    if (!portfolio || portfolio.positions.length === 0) return MOCK_HOLDINGS;
    const assets = Number(portfolio.total_assets);
    return portfolio.positions.map((position) => {
      const matched = MOCK_HOLDINGS.find((holding) => STOCK_INFO[holding.name]?.code === position.stock_code);
      const metadata = matched ?? MOCK_HOLDINGS[0];
      return {
        ...metadata,
        name: matched?.name ?? position.stock_code,
        pct: assets > 0 ? Number(position.evaluation_amount) / assets * 100 : 0,
        chg: Number(position.return_rate),
        principal: Number(position.purchase_amount),
        returnRate: Number(position.return_rate),
      };
    });
  }, [portfolio]);

  // 리밸런싱 "조정 전/후" 상세 시트
  const [rebalanceSheetId, setRebalanceSheetId] = useState<string | null>(null);
  // 시트의 두 액션("조정하기"/"이번에는 하지 않을게요")이 실제로 다른 결과를 남기도록, 제안 id별로
  // 어떤 결정을 내렸는지 세션 동안 기억한다 — PortfolioDetail 의 같은 위젯과 동일한 패턴.
  const [alertDecisions, setAlertDecisions] = useState<Record<string, 'adjusted' | 'held'>>({});
  const rebalanceAlert = AI_ALERTS.find((a) => a.id === rebalanceSheetId) ?? null;
  const rebalanceHolding = rebalanceAlert ? ALL_HOLDINGS.find((h) => h.name === rebalanceAlert.stockName) : undefined;
  const rebalanceTargetPct = rebalanceHolding ? rebalanceHolding.target ?? rebalanceHolding.pct : 0;
  const rebalanceAdjustAmount = rebalanceHolding
    ? Math.round((HOLD_TOTAL * (rebalanceHolding.pct - rebalanceTargetPct)) / 100)
    : 0;

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <button onClick={onBack} className="self-start text-[15px] text-muted">← 돌아가기</button>

          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-[#3F5222]">✦ AI의 리밸런싱 제안</span>
            <h1 className="text-[38px] font-bold leading-[52px] tracking-[-0.03em]">지금 확인해야 할 손절·리밸런싱 제안이 있어요</h1>
            <span className="text-[17px] text-subtle">총 {AI_ALERTS.length}건</span>
          </section>

          <section className="flex flex-col gap-4 rounded-card bg-surface p-6">
            {AI_ALERTS.length === 0 ? (
              <p className="px-6 py-10 text-center text-[17px] text-subtle">확인할 제안이 없어요.</p>
            ) : (
              AI_ALERTS.map((a) => {
                const decision = alertDecisions[a.id];
                return (
                  <div key={a.id} className="flex items-center justify-between gap-6 rounded-[20px] bg-canvas px-9 py-7">
                    <div className="flex flex-col gap-2">
                      <div className="flex items-center gap-2.5">
                        <span className={`rounded-full px-3 py-1.5 text-sm font-bold ${ALERT_BADGE[a.kind]}`}>{a.badge}</span>
                        <span className="text-[19px] font-bold tracking-[-0.02em]">{a.stockName}</span>
                        {decision && (
                          <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold ${
                            decision === 'adjusted' ? 'bg-[#F8FCEE] text-[#3F5222]' : 'bg-[#F4F6F1] text-muted'
                          }`}>
                            {decision === 'adjusted' ? '✓ 승인함' : '보류함'}
                          </span>
                        )}
                      </div>
                      <p className="text-[16px] text-muted">{a.headline}</p>
                    </div>
                    <button
                      onClick={() => setRebalanceSheetId(a.id)}
                      className={`shrink-0 rounded-field px-6 py-3.5 text-[15px] font-bold ${
                        decision ? 'bg-[#F4F6F1] text-[#3F4A43]' : 'bg-lime text-navy'
                      }`}
                    >
                      {decision ? '결정 다시 보기' : (a.kind === '리밸런싱' ? '조정 제안 확인하기' : '손절 조치 확인하기')}
                    </button>
                  </div>
                );
              })
            )}
          </section>
        </div>
      </main>

      {/* 리밸런싱 "조정 전/후" 상세 시트 — 손절 제안은 목표 비중 개념이 없어 AI 제안 액션을 대신 보여준다.
          "조정 제안/손절 조치 확인하기" 클릭 시 연다 */}
      {rebalanceAlert && rebalanceHolding && (
        <div className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8" onClick={() => setRebalanceSheetId(null)}>
          <div className="flex w-[720px] flex-col gap-7 rounded-card bg-surface p-12" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-6">
              <h2 className="text-[28px] font-bold leading-10 tracking-[-0.03em]">
                {rebalanceAlert.kind === '리밸런싱' ? '왜 지금 비중을 조정하라고 하나요?' : '왜 지금 정리하는 게 좋을까요?'}
              </h2>
              <button aria-label="닫기" onClick={() => setRebalanceSheetId(null)} className="rounded-[9px] bg-canvas p-2 text-muted">
                <X size={18} />
              </button>
            </div>
            <p className="text-lg leading-[30px] text-[#3F4A43]">{rebalanceAlert.reason}</p>
            {rebalanceAlert.kind === '리밸런싱' ? (
              <div className="flex items-center gap-6 rounded-[18px] bg-canvas px-8 py-7">
                <div className="flex flex-1 flex-col gap-2">
                  <span className="text-[15px] text-muted">현재</span>
                  <span className="text-[28px] font-bold tracking-[-0.03em] text-warn">{rebalanceHolding.pct.toFixed(1)}%</span>
                  <div className="h-2.5 rounded-full bg-[#E5E9E3]"><div className="h-2.5 rounded-full bg-warn" style={{ width: `${rebalanceHolding.pct}%` }} /></div>
                </div>
                <span className="text-2xl text-[#A6AFA7]">→</span>
                <div className="flex flex-1 flex-col gap-2">
                  <span className="text-[15px] text-muted">조정 후</span>
                  <span className="text-[28px] font-bold tracking-[-0.03em]">{rebalanceTargetPct.toFixed(1)}%</span>
                  <div className="h-2.5 rounded-full bg-[#E5E9E3]"><div className="h-2.5 rounded-full bg-navy" style={{ width: `${rebalanceTargetPct}%` }} /></div>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 rounded-[18px] bg-canvas px-8 py-7">
                <span className="shrink-0 text-[15px] font-semibold text-[#3F5222]">AI 제안</span>
                <span className="text-[17px] font-semibold text-ink">{rebalanceAlert.action}</span>
              </div>
            )}
            <div className="flex flex-col gap-2.5 rounded-[18px] bg-[#F8FCEE] px-8 py-7">
              <span className="text-lg font-bold tracking-[-0.02em]">
                {rebalanceAlert.kind === '리밸런싱' ? '조정하지 않으면?' : '정리하지 않으면?'}
              </span>
              <p className="text-[17px] leading-7 text-[#3F4A43]">
                특정 종목의 영향이 커져 {selectedStrategy.name}보다 포트폴리오가 더 많이 흔들릴 수 있어요.
              </p>
            </div>
            {alertDecisions[rebalanceAlert.id] ? (
              <div className="flex items-center gap-4 rounded-[18px] bg-[#F4F6F1] px-8 py-7">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-lime text-navy">
                  <Check size={18} />
                </span>
                <div className="flex flex-1 flex-col gap-1">
                  <span className="text-[17px] font-bold text-ink">
                    {alertDecisions[rebalanceAlert.id] === 'adjusted' ? '이 제안을 승인했어요' : '이번엔 보류했어요'}
                  </span>
                  <span className="text-[15px] text-muted">
                    {alertDecisions[rebalanceAlert.id] === 'adjusted'
                      ? 'AI가 다음 리밸런싱에 반영해요.'
                      : '다음에 다시 확인할 수 있어요.'}
                  </span>
                </div>
                <button onClick={() => setRebalanceSheetId(null)} className="shrink-0 rounded-field bg-navy px-6 py-3.5 text-[15px] font-bold text-white">
                  닫기
                </button>
              </div>
            ) : (
              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setAlertDecisions((prev) => ({ ...prev, [rebalanceAlert.id]: 'adjusted' }));
                    setRebalanceSheetId(null);
                  }}
                  className="flex-1 rounded-field bg-lime py-5 text-lg font-bold text-navy"
                >
                  {rebalanceAlert.kind === '리밸런싱' ? `${won(Math.abs(rebalanceAdjustAmount))} 조정하기` : '제안대로 정리하기'}
                </button>
                <button
                  onClick={() => {
                    setAlertDecisions((prev) => ({ ...prev, [rebalanceAlert.id]: 'held' }));
                    setRebalanceSheetId(null);
                  }}
                  className="rounded-field bg-[#F4F6F1] px-8 py-5 text-[17px] font-semibold text-[#3F4A43]"
                >
                  이번에는 하지 않을게요
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
