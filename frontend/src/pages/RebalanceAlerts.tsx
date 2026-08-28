import { useMemo, useState } from 'react';
import { Check, X } from 'lucide-react';
import Header from '../components/Header';
import { buildDetailedPortfolioHoldings } from '../lib/portfolioModel';
import { useTradingData } from '../hooks/useTradingData';
import type { StrategyResponse } from '../lib/backendApi';
import { getDisplayAlerts } from '../lib/rebalancing';
import { won } from '../lib/validation';
import { useTradingStore } from '../store/tradingStore';
import type { Screen } from '../types';
import PortfolioDataState from '../components/PortfolioDataState';
import { useTradingRetry } from '../hooks/useTradingRetry';

interface Props {
  userName: string;
  strategy: StrategyResponse;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
  /** 자동매매(activeMode==='auto') 유저가 실 계좌 없이(portfolio===null) 이 화면에 들어온 경우에만
   *  mock(AI_ALERTS) 과거형/완료 톤을 쓴다 — portfolio!==null 하나만으로 판단하면, 반자동 유저도
   *  포트폴리오 로딩 중이거나 조회에 실패해 portfolio가 잠깐/계속 null인 동안 완료 톤으로 잘못 보인다.
   *  반자동은 이 값과 무관하게 항상 "제안" 톤이어야 한다. */
  isAutoMode: boolean;
  onAccountMissingAction?: () => void;
}

/** AI 제안 종류별 배지 색 — PortfolioDetail 의 요약 카드와 동일한 배색을 공유한다 */
const ALERT_BADGE: Record<'손절' | '리밸런싱', string> = {
  '손절': 'bg-[#FBEAEA] text-up',
  '리밸런싱': 'bg-[#FCF3E4] text-warn',
};

/** `/rebalance-alerts` — AI 손절·리밸런싱 제안 전체 목록. PortfolioDetail "AI의 리밸런싱 제안"의 "더보기"에서 진입한다.
 *  실 계좌에 리밸런싱 제안(규칙기반)이 있으면 그 값을, 없으면 AI_ALERTS(목업)를 그대로 쓴다 — lib/rebalancing.ts 참고. */
function RebalanceAlertsContent({ userName, strategy, onNavigate, onBack, isAutoMode }: Props) {
    const portfolio = useTradingStore((state) => state.portfolio);
  // 계좌 자체가 없다고 "확인된" 상태(404) — 이 값만 mock 전환의 기준으로 쓴다. portfolio===null은
  // "계좌 없음"과 "계좌는 있는데 아직 로딩 중/조회 실패"를 구분하지 못해(둘 다 null) 기준으로 삼지 않는다.
  const accountMissing = useTradingStore((state) => state.accountMissing);
  const isLoading = useTradingStore((state) => state.isLoading);
  const error = useTradingStore((state) => state.error);
  
  const displayAlerts = useMemo(() => getDisplayAlerts(portfolio), [portfolio]);

  

  // displayAlerts는 실 계좌가 있으면(portfolio) portfolio.rebalancing_proposals(아직 실행 전인 "제안")를,
  // 없으면 AI_ALERTS(이미 실행됐다는 설정의 스토리 목업)를 쓴다 — lib/rebalancing.ts 참고. 그래서 자동매매
  // 실계좌라도 제안은 아직 제안일 뿐이라, 실데이터면 반자동과 같은 "제안" 톤을 쓰고 mock일 때만 과거형/완료
  // 톤을 써야 한다. 다만 portfolio!==null만으로 판단하면 반자동 유저도 로딩 중/조회 실패로 portfolio가
  // 잠깐 null인 동안 완료 톤으로 잘못 보일 수 있어, 애초에 자동매매가 아니면(!isAutoMode) 실데이터 여부와
  // 무관하게 항상 "제안" 톤을 쓰도록 activeMode를 우선 확인한다.
  const usingRealAlerts = true;

  // 계좌가 없다고 확인된 경우(accountMissing)에만 목업 20종목을 쓰고, 그 외(실 계좌 포지션이 0개, 또는
  // 아직 로딩 중/조회 실패로 portfolio를 못 받은 경우)에는 빈 배열/0원을 써서 실제 빈 상태로 보여준다.
  const HOLD_TOTAL = Number(portfolio?.total_assets ?? 0);
    const ALL_HOLDINGS = useMemo(
    () => buildDetailedPortfolioHoldings(portfolio),
    [portfolio],
  );

  // 리밸런싱 "조정 전/후" 상세 시트
  const [rebalanceSheetId, setRebalanceSheetId] = useState<string | null>(null);
  // 시트의 두 액션("조정하기"/"이번에는 하지 않을게요")이 실제로 다른 결과를 남기도록, 제안 id별로
  // 어떤 결정을 내렸는지 세션 동안 기억한다 — PortfolioDetail 의 같은 위젯과 동일한 패턴.
  const [alertDecisions, setAlertDecisions] = useState<Record<string, 'adjusted' | 'held'>>({});
  const rebalanceAlert = displayAlerts.find((a) => a.id === rebalanceSheetId) ?? null;
    const rebalanceHolding = rebalanceAlert
  ? ALL_HOLDINGS.find((h) => h.stockCode === rebalanceAlert.stockCode)
  : undefined;
  // 실 제안이면 API가 이미 계산해 준 현재/목표 비중·조정금액을 그대로 쓴다 — 목업일 때만 보유 종목 목록에서
  // 같은 이름을 찾아(이름 매칭이라 실패할 수 있음) 대신 파생시킨다.
  const rebalanceCurrentPct = rebalanceAlert?.currentWeight ?? (rebalanceHolding ? rebalanceHolding.pct : 0);
  const rebalanceTargetPct = rebalanceAlert?.targetWeight ?? 0;
    const rebalanceAdjustAmount = rebalanceAlert?.recommendedAmount ?? 0;

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <button onClick={onBack} className="self-start text-[15px] text-muted">← 돌아가기</button>

          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-[#3F5222]">
              {!usingRealAlerts ? '✦ AI가 자동으로 처리했어요' : '✦ AI의 리밸런싱 제안'}
            </span>
            <h1 className="text-[38px] font-bold leading-[52px] tracking-[-0.03em]">
              {!usingRealAlerts ? 'AI가 자동으로 실행한 손절·리밸런싱 내역이에요' : '지금 확인해야 할 손절·리밸런싱 제안이 있어요'}
            </h1>
            <span className="text-[17px] text-subtle">총 {displayAlerts.length}건</span>
          </section>

          <section className="flex flex-col gap-4 rounded-card bg-surface p-6">
            {displayAlerts.length === 0 ? (
              <p className="px-6 py-10 text-center text-[17px] text-subtle">
                {!usingRealAlerts ? '최근 자동 실행 내역이 없어요.' : '확인할 제안이 없어요.'}
              </p>
            ) : (
              displayAlerts.map((a) => {
                const decision = alertDecisions[a.id];
                return (
                  <div key={a.id} className="flex items-center justify-between gap-6 rounded-[20px] bg-canvas px-9 py-7">
                    <div className="flex flex-col gap-2">
                      <div className="flex items-center gap-2.5">
                        <span className={`rounded-full px-3 py-1.5 text-sm font-bold ${ALERT_BADGE[a.kind]}`}>{a.badge}</span>
                        <span className="text-[19px] font-bold tracking-[-0.02em]">{a.stockName}</span>
                        {/* 자동매매는 이미 실행이 끝난 내역이라 승인/보류 결정 상태 대신 항상 완료 배지를 보여준다 */}
                        {!usingRealAlerts ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-[#F8FCEE] px-2.5 py-1 text-xs font-bold text-[#3F5222]">
                            <Check size={12} /> 완료
                          </span>
                        ) : decision && (
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
                        !usingRealAlerts || decision ? 'bg-[#F4F6F1] text-[#3F4A43]' : 'bg-lime text-navy'
                      }`}
                    >
                      {!usingRealAlerts ? '실행 내역 보기' : decision ? '결정 다시 보기' : (a.kind === '리밸런싱' ? '조정 제안 확인하기' : '손절 조치 확인하기')}
                    </button>
                  </div>
                );
              })
            )}
          </section>
        </div>
      </main>

      {/* 리밸런싱 "조정 전/후" 상세 시트 — 손절 제안은 목표 비중 개념이 없어 AI 제안 액션을 대신 보여준다.
          "조정 제안/손절 조치 확인하기" 클릭 시 연다. 자동매매는 이미 실행된 내역이라 "조정하지 않으면?"
          같은 승인 유도 문구·조정/보류 버튼이 맞지 않아, PortfolioAuto.tsx의 alertModal과 같은 톤(과거형
          제목, 결정 버튼 없이 확인만)으로 대신 보여준다. */}
      {rebalanceAlert && (
        <div className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8" onClick={() => setRebalanceSheetId(null)}>
          <div className="flex w-[720px] flex-col gap-7 rounded-card bg-surface p-12" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-6">
              <h2 className="text-[28px] font-bold leading-10 tracking-[-0.03em]">
                {!usingRealAlerts
                  ? (rebalanceAlert.kind === '리밸런싱' ? '왜 이렇게 조정했나요?' : '왜 이렇게 정리했나요?')
                  : (rebalanceAlert.kind === '리밸런싱' ? '왜 지금 비중을 조정하라고 하나요?' : '왜 지금 정리하는 게 좋을까요?')}
              </h2>
              <button aria-label="닫기" onClick={() => setRebalanceSheetId(null)} className="rounded-[9px] bg-canvas p-2 text-muted">
                <X size={18} />
              </button>
            </div>
            <p className="text-lg leading-[30px] text-[#3F4A43]">{rebalanceAlert.reason}</p>
            {rebalanceAlert.kind === '리밸런싱' ? (
              <div className="flex items-center gap-6 rounded-[18px] bg-canvas px-8 py-7">
                <div className="flex flex-1 flex-col gap-2">
                  <span className="text-[15px] text-muted">{!usingRealAlerts ? '조정 전' : '현재'}</span>
                  <span className="text-[28px] font-bold tracking-[-0.03em] text-warn">{rebalanceCurrentPct.toFixed(1)}%</span>
                  <div className="h-2.5 rounded-full bg-[#E5E9E3]"><div className="h-2.5 rounded-full bg-warn" style={{ width: `${rebalanceCurrentPct}%` }} /></div>
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
                <span className="shrink-0 text-[15px] font-semibold text-[#3F5222]">{!usingRealAlerts ? 'AI 조치' : 'AI 제안'}</span>
                <span className="text-[17px] font-semibold text-ink">{rebalanceAlert.action}</span>
              </div>
            )}
            {usingRealAlerts && (
              <div className="flex flex-col gap-2.5 rounded-[18px] bg-[#F8FCEE] px-8 py-7">
                <span className="text-lg font-bold tracking-[-0.02em]">
                  {rebalanceAlert.kind === '리밸런싱' ? '조정하지 않으면?' : '정리하지 않으면?'}
                </span>
                <p className="text-[17px] leading-7 text-[#3F4A43]">
                  특정 종목의 영향이 커져 {strategy.name}보다 포트폴리오가 더 많이 흔들릴 수 있어요.
                </p>
              </div>
            )}
            {!usingRealAlerts ? (
              <div className="flex items-center gap-4 rounded-[18px] bg-[#F4F6F1] px-8 py-7">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-lime text-navy">
                  <Check size={18} />
                </span>
                <div className="flex flex-1 flex-col gap-1">
                  <span className="text-[17px] font-bold text-ink">AI가 이미 실행을 마쳤어요</span>
                  <span className="text-[15px] text-muted">다음 리밸런싱도 전략에 맞춰 자동으로 진행돼요.</span>
                </div>
                <button onClick={() => setRebalanceSheetId(null)} className="shrink-0 rounded-field bg-navy px-6 py-3.5 text-[15px] font-bold text-white">
                  확인했어요
                </button>
              </div>
            ) : alertDecisions[rebalanceAlert.id] ? (
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

export default function RebalanceAlerts(props: Props) {
  useTradingData();
  const loading = useTradingStore((state) => state.isLoading);
  const accountMissing = useTradingStore((state) => state.accountMissing);
  const error = useTradingStore((state) => state.error);
  const retry = useTradingRetry();
  if (loading || accountMissing || error) {
    return <PortfolioDataState userName={props.userName} onNavigate={props.onNavigate} loading={loading} accountMissing={accountMissing} error={error} onRetry={retry} onAccountMissingAction={props.onAccountMissingAction}><div /></PortfolioDataState>;
  }
  return <RebalanceAlertsContent {...props} />;
}

