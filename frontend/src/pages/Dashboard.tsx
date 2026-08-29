import { useRef, useState } from "react";
import { X } from "lucide-react";
import Header from "../components/Header";
import { useTradingData } from "../hooks/useTradingData";
import { won } from "../lib/validation";
import type { OperationMode } from "../data/fees";
import type { StrategyResponse } from "../lib/backendApi";
import {
  strategyRebalanceLabel,
  strategyRiskLabel,
} from "../lib/strategyCatalog";
import { useTradingStore } from "../store/tradingStore";
import type { Screen } from "../types";

interface Props {
  userName: string;
  strategy: StrategyResponse;
  /** 실제 투자 시작 시점의 운용방식 — null이면 판단할 수 없는 상태로, 안전하게 "확인하고 실행" 쪽 UI를 기본값으로 쓴다 */
  mode: OperationMode | null;
  onNavigate: (s: Screen) => void;
  onOpenHoldings: () => void;
  onChangeStrategy: () => void;
}

/** 05 포트폴리오 대시보드 — 스토리 → 리밸런싱 제안(운용방식별 분기) → 판단 성적표 → 전략 */
export default function Dashboard({
  userName,
  strategy,
  mode,
  onNavigate,
  onOpenHoldings,
  onChangeStrategy,
}: Props) {
  const isAuto = mode === "auto";
  const token = useTradingData();
  const account = useTradingStore((state) => state.account);
  const portfolio = useTradingStore((state) => state.portfolio);
  const decisions = useTradingStore((state) => state.decisions);
  const recordDecision = useTradingStore((state) => state.recordDecision);
  const isDecisionSubmitting = useTradingStore(
    (state) => state.isDecisionSubmitting,
  );
  const [sheetOpen, setSheetOpen] = useState(false); // 리밸런싱 상세 시트
  const decisionRetry = useRef<{
    decision: "ACCEPTED" | "HELD";
    accountId: string;
    stockCode: string;
    proposalKey: string;
    key: string;
  } | null>(null);

  const top = portfolio?.top_contributor ?? null;
  const topName = top?.stock_name ?? top?.stock_code ?? null;
  const topAmount = top ? Number(top.amount) : null;
  const proposal = portfolio?.rebalancing_proposals[0] ?? null;
  const holdTotal = portfolio ? Number(portfolio.total_assets) : null;
  const initialCash = account ? Number(account.initial_cash) : 0;
  const profit =
    portfolio && initialCash > 0
      ? Number(portfolio.total_assets) - initialCash
      : null;
  const profitRate =
    profit != null && initialCash > 0 ? (profit / initialCash) * 100 : null;
  const latestDecision = decisions?.items[0] ?? null;
  const actualOutcome =
    latestDecision?.actual_portfolio_return_rate == null
      ? null
      : Number(latestDecision.actual_portfolio_return_rate);
  const submitDecision = async (decision: "ACCEPTED" | "HELD") => {
    if (!token || !account || !proposal || !proposal.proposal_key) return;
    const retry =
      decisionRetry.current?.decision === decision &&
      decisionRetry.current.accountId === account.id &&
      decisionRetry.current.stockCode === proposal.stock_code &&
      decisionRetry.current.proposalKey === proposal.proposal_key
        ? decisionRetry.current
        : {
            decision,
            accountId: account.id,
            stockCode: proposal.stock_code,
            proposalKey: proposal.proposal_key,
            key: crypto.randomUUID(),
          };
    decisionRetry.current = retry;
    try {
      await recordDecision(token, {
        account_id: account.id,
        stock_code: proposal.stock_code,
        proposal_key: proposal.proposal_key,
        decision,
        idempotency_key: retry.key,
      });
      decisionRetry.current = null;
      setSheetOpen(false);
    } catch {
      // Store에 실제 API 오류가 보존되므로 시트를 유지해 사용자가 다시 시도할 수 있게 한다.
    }
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-16">
          <section className="flex flex-col gap-5">
            <span className="text-base font-semibold text-muted">
              오늘의 포트폴리오
            </span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
              {userName}님의 투자는
              <br />
              오늘도 전략대로 움직이고 있어요.
            </h1>
            <div className="flex items-baseline gap-4">
              <span className="text-[32px] font-bold tracking-[-0.03em]">
                {holdTotal == null ? "-" : won(holdTotal)}
              </span>
              <span className="text-[19px] font-semibold text-up">
                {profit == null || profitRate == null
                  ? "-"
                  : `${profit >= 0 ? "+" : ""}${Math.round(profit).toLocaleString("ko-KR")}원 (${profitRate >= 0 ? "+" : ""}${profitRate.toFixed(2)}%)`}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-2 rounded-full bg-[#EAF7EF] px-3.5 py-2 text-[15px] font-semibold text-[#2E9B65]">
                ● 전략 정상
              </span>
              <span className="text-[17px] text-muted">
                {portfolio?.strategy_targets_available
                  ? `현재 포트폴리오를 ${strategy.name} 목표 비중과 비교했어요.`
                  : "전략 목표 비중 데이터가 아직 없어요."}
              </span>
            </div>
          </section>

          {/* 포트폴리오 스토리 — 의미 → 숫자 순서 */}
          <section className="flex flex-col gap-6">
            <h2 className="text-[32px] font-bold leading-[46px] tracking-[-0.03em]">
              오늘 내 투자에는 무슨 일이 있었나요?
            </h2>
            <div className="flex flex-col gap-4">
              <Story
                title={
                  topName
                    ? `${topName}가 오늘 수익을 가장 많이 만들었어요`
                    : "오늘 종목별 기여 데이터가 아직 없어요"
                }
              >
                <div className="flex items-baseline gap-4">
                  <span className="text-2xl font-bold text-up">
                    {topAmount == null
                      ? "-"
                      : `${topAmount >= 0 ? "+" : ""}${Math.round(topAmount).toLocaleString("ko-KR")}원`}
                  </span>
                  <span className="text-[17px] text-muted">
                    {top?.share_rate == null
                      ? "-"
                      : `오늘 전체 수익의 ${Math.round(Number(top.share_rate))}%`}
                  </span>
                </div>
                {top == null && (
                  <span className="text-sm text-subtle">
                    실제 당일 기여도 데이터가 아직 없어요.
                  </span>
                )}
              </Story>

              <Story
                title={
                  proposal
                    ? `${proposal.stock_name ?? proposal.stock_code} 비중을 조정할 필요가 있어요`
                    : "현재 확인할 리밸런싱 제안이 없어요"
                }
              >
                <div className="flex items-center gap-3.5 text-[19px] text-[#3F4A43]">
                  <span>
                    목표{" "}
                    {proposal
                      ? `${Number(proposal.target_weight).toFixed(1)}%`
                      : "-"}
                  </span>
                  <span className="text-[#A6AFA7]">→</span>
                  <span className="font-bold">
                    현재{" "}
                    {proposal
                      ? `${Number(proposal.current_weight).toFixed(1)}%`
                      : "-"}
                  </span>
                </div>
                <span className="text-[17px] leading-7 text-muted">
                  어떻게 하면 좋을지 아래에서 AI 제안을 확인해보세요.
                </span>
              </Story>

              <Story title="실제 계좌와 시장 데이터를 우선 사용해요">
                <span className="text-[17px] leading-7 text-muted">
                  아직 연동되지 않은 설명·재무·분석 항목만 기존 데모 값으로
                  보완해요.
                </span>
              </Story>
            </div>
          </section>

          {/* 리밸런싱 — 확인하고 실행은 제안(사용자 실행 필요), 자동으로 운용은 이미 처리된 상태를 안내 */}
          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <div className="flex gap-5">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-lime text-lg text-navy">
                ✦
              </div>
              <div className="flex flex-1 flex-col gap-4">
                <span className="text-[26px] font-bold tracking-[-0.025em]">
                  {isAuto
                    ? "물방개가 운용 중이에요"
                    : "AI가 확인할 게 하나 있어요"}
                </span>
                <p className="max-w-[720px] text-lg leading-[30px] text-[#3F4A43]">
                  {isAuto
                    ? proposal
                      ? `${proposal.stock_name ?? proposal.stock_code} 비중 조정안을 확인했어요.`
                      : "현재 실행할 수 있는 실제 비중 조정안이 없어요."
                    : proposal
                      ? `${proposal.stock_name ?? proposal.stock_code} 비중이 전략 목표와 달라졌어요.`
                      : "현재 확인할 수 있는 실제 비중 조정안이 없어요."}
                </p>
                <div className="flex gap-10 rounded-[18px] bg-canvas px-8 py-6">
                  <Fact
                    label="목표"
                    value={
                      proposal
                        ? `${Number(proposal.target_weight).toFixed(1)}%`
                        : "-"
                    }
                  />
                  <Fact
                    label={isAuto ? "조정 전" : "현재"}
                    value={
                      proposal
                        ? `${Number(proposal.current_weight).toFixed(1)}%`
                        : "-"
                    }
                    warn
                  />
                  {isAuto ? (
                    <Fact
                      label="조정 후"
                      value={
                        proposal
                          ? `${Number(proposal.target_weight).toFixed(1)}%`
                          : "-"
                      }
                    />
                  ) : (
                    <Fact
                      label="추천"
                      value={
                        proposal
                          ? `${won(Number(proposal.recommended_amount))} ${proposal.action === "SELL" ? "줄이기" : "늘리기"}`
                          : "-"
                      }
                    />
                  )}
                </div>
                <div className="flex items-center gap-3 pt-1">
                  {isAuto ? (
                    <button
                      disabled={!proposal}
                      onClick={() => setSheetOpen(true)}
                      className="text-base font-semibold text-navy underline disabled:text-muted"
                    >
                      자세히 보기 →
                    </button>
                  ) : (
                    <button
                      disabled={!proposal}
                      onClick={() => setSheetOpen(true)}
                      className="rounded-field bg-lime px-8 py-4 text-[17px] font-bold text-navy disabled:opacity-50"
                    >
                      제안 확인하기
                    </button>
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* 포트폴리오 시각화 진입 */}
          <section className="flex items-center justify-between gap-8 rounded-card bg-surface px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-2xl font-bold tracking-[-0.025em]">
                내 돈은 지금 이렇게 나뉘어 있어요
              </span>
              <span className="text-[17px] leading-7 text-muted">
                {portfolio
                  ? `${portfolio.positions.length}개 종목의 현재 비중과 오늘 등락을 한 번에 볼 수 있어요.`
                  : "보유 종목 데이터를 불러오고 있어요."}
              </span>
            </div>
            <button
              onClick={onOpenHoldings}
              className="shrink-0 rounded-field bg-[#F4F6F1] px-7 py-4 text-[17px] font-semibold text-[#3F4A43]"
            >
              전체 보유 종목 보기 →
            </button>
          </section>

          {/* 판단 성적표 — 평가가 아니라 기록 */}
          <section className="flex flex-col gap-6">
            <div className="flex flex-col gap-3.5">
              <h2 className="text-[32px] font-bold leading-[46px] tracking-[-0.03em]">
                내 투자 판단은 어땠을까요?
              </h2>
              <p className="text-lg leading-[30px] text-muted">
                AI 제안을 따랐을 때와 내가 선택한 결과를 함께 돌아볼 수 있어요.
              </p>
            </div>
            <div className="flex flex-col gap-5 rounded-card bg-surface p-12">
              <div className="flex flex-col gap-3">
                <span className="text-[15px] text-muted">지난 리밸런싱</span>
                <div className="flex items-center gap-3.5 text-[19px] text-[#3F4A43]">
                  <span>
                    AI 제안{" "}
                    <b>
                      {latestDecision
                        ? `${latestDecision.stock_name ?? latestDecision.stock_code} ${latestDecision.action === "SELL" ? "줄이기" : "늘리기"}`
                        : "-"}
                    </b>
                  </span>
                  <span className="text-[#A6AFA7]">·</span>
                  <span>
                    내 선택{" "}
                    <b>
                      {latestDecision
                        ? latestDecision.decision === "ACCEPTED"
                          ? "수락"
                          : "보류"
                        : "-"}
                    </b>
                  </span>
                </div>
                <span className="text-[17px] text-muted">
                  {latestDecision
                    ? actualOutcome == null
                      ? "다음 일별 스냅샷부터 실제 결과를 비교할 수 있어요."
                      : `${latestDecision.outcome_as_of} 기준 포트폴리오 ${actualOutcome >= 0 ? "+" : ""}${actualOutcome.toFixed(2)}%`
                    : "아직 기록된 리밸런싱 판단이 없어요."}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-2 rounded-[18px] bg-canvas px-8 py-7">
                  <span className="text-[15px] text-muted">
                    최근 6개월 수락
                  </span>
                  <span className="text-[26px] font-bold tracking-[-0.03em]">
                    {decisions?.accepted ?? 0}건
                  </span>
                </div>
                <div className="flex flex-col gap-2 rounded-[18px] bg-canvas px-8 py-7">
                  <span className="text-[15px] text-muted">
                    최근 6개월 보류
                  </span>
                  <span className="text-[26px] font-bold tracking-[-0.03em]">
                    {decisions?.held ?? 0}건
                  </span>
                </div>
              </div>
              <p className="text-[17px] leading-7 text-muted">
                각 판단 결과는 판단 시점 자산과 이후 실제 계좌 스냅샷을 기준으로
                개별 확인해요.
              </p>
              <span className="text-base font-semibold text-navy">
                지난 판단 돌아보기 →
              </span>
            </div>
          </section>

          {/* 전략 변경 — Primary 로 강조하지 않는다 */}
          <section className="flex items-center justify-between gap-8 rounded-card bg-surface px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-[15px] text-muted">현재 전략</span>
              <span className="text-2xl font-bold tracking-[-0.025em]">
                {strategy.name}
              </span>
              <span className="text-base text-muted">
                위험도 {strategyRiskLabel(strategy.risk_level)} · 리밸런싱{" "}
                {strategyRebalanceLabel(strategy.rebalance_cycle)}
              </span>
            </div>
            <button
              onClick={onChangeStrategy}
              className="shrink-0 rounded-field bg-[#F4F6F1] px-7 py-4 text-[17px] font-semibold text-[#3F4A43]"
            >
              전략 변경하기
            </button>
          </section>
        </div>
      </main>

      {/* 05_Rebalancing_Detail — Before → After */}
      {sheetOpen && proposal && (
        <div
          className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8"
          onClick={() => setSheetOpen(false)}
        >
          <div
            className="flex w-[720px] flex-col gap-7 rounded-card bg-surface p-12"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-6">
              <h2 className="text-[28px] font-bold leading-10 tracking-[-0.03em]">
                {isAuto
                  ? "왜 비중을 조정했나요?"
                  : "왜 지금 비중을 조정하라고 하나요?"}
              </h2>
              <button
                aria-label="닫기"
                onClick={() => setSheetOpen(false)}
                className="rounded-[9px] bg-canvas p-2 text-muted"
              >
                <X size={18} />
              </button>
            </div>
            <p className="text-lg leading-[30px] text-[#3F4A43]">
              {proposal.stock_name ?? proposal.stock_code}의 현재 비중과 전략
              목표 비중을 실제 평가금액 기준으로 비교했어요.
            </p>
            <div className="flex items-center gap-6 rounded-[18px] bg-canvas px-8 py-7">
              <div className="flex flex-1 flex-col gap-2">
                <span className="text-[15px] text-muted">현재</span>
                <span className="text-[28px] font-bold tracking-[-0.03em] text-warn">
                  {Number(proposal.current_weight).toFixed(1)}%
                </span>
                <div className="h-2.5 rounded-full bg-[#E5E9E3]">
                  <div
                    className="h-2.5 rounded-full bg-warn"
                    style={{
                      width: `${Math.min(Number(proposal.current_weight), 100)}%`,
                    }}
                  />
                </div>
              </div>
              <span className="text-2xl text-[#A6AFA7]">→</span>
              <div className="flex flex-1 flex-col gap-2">
                <span className="text-[15px] text-muted">조정 후</span>
                <span className="text-[28px] font-bold tracking-[-0.03em]">
                  {Number(proposal.target_weight).toFixed(1)}%
                </span>
                <div className="h-2.5 rounded-full bg-[#E5E9E3]">
                  <div
                    className="h-2.5 rounded-full bg-navy"
                    style={{
                      width: `${Math.min(Number(proposal.target_weight), 100)}%`,
                    }}
                  />
                </div>
              </div>
            </div>
            <div className="flex flex-col gap-2.5 rounded-[18px] bg-[#F8FCEE] px-8 py-7">
              <span className="text-lg font-bold tracking-[-0.02em]">
                {isAuto ? "조정하지 않았다면?" : "조정하지 않으면?"}
              </span>
              <p className="text-[17px] leading-7 text-[#3F4A43]">
                특정 종목의 영향이 커져 저변동성 전략보다 포트폴리오가 더 많이
                흔들릴 수 있어요.
              </p>
            </div>
            {isAuto ? (
              <button
                onClick={() => setSheetOpen(false)}
                className="rounded-field bg-lime py-5 text-lg font-bold text-navy"
              >
                확인했어요
              </button>
            ) : (
              <div className="flex gap-3">
                <button
                  disabled={isDecisionSubmitting}
                  onClick={() => void submitDecision("ACCEPTED")}
                  className="flex-1 rounded-field bg-lime py-5 text-lg font-bold text-navy disabled:opacity-50"
                >
                  제안 수락 기록하기
                </button>
                <button
                  disabled={isDecisionSubmitting}
                  onClick={() => void submitDecision("HELD")}
                  className="rounded-field bg-[#F4F6F1] px-8 py-5 text-[17px] font-semibold text-[#3F4A43] disabled:opacity-50"
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

function Story({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3.5 rounded-card bg-surface px-11 py-10">
      <span className="text-[26px] font-bold leading-[38px] tracking-[-0.025em]">
        {title}
      </span>
      {children}
    </div>
  );
}

function Fact({
  label,
  value,
  warn,
}: {
  label: string;
  value: string;
  warn?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[15px] text-muted">{label}</span>
      <span className={`text-xl font-bold ${warn ? "text-warn" : ""}`}>
        {value}
      </span>
    </div>
  );
}
