import { useEffect, useMemo, useRef, useState } from "react";
import { Check, X } from "lucide-react";
import Header from "../components/Header";
import { buildDetailedPortfolioHoldings } from "../lib/portfolioModel";
import { toAccountOperationMode } from "../data/fees";
import { useTradingData } from "../hooks/useTradingData";
import {
  ApiError,
  getPortfolioComparisonApi,
  rebalanceLatestLossAvoidanceRecommendationApi,
  rebalanceLatestModelRecommendationsApi,
  type PortfolioComparisonResponse,
  type PortfolioHistoryPeriod,
  type StrategyResponse,
} from "../lib/backendApi";
import {
  getDisplayDecisions,
  type DisplayDecisionSummary,
} from "../lib/decisions";
import { getDisplayAlerts } from "../lib/rebalancing";
import {
  strategyRebalanceLabel,
  strategyRiskLabel,
} from "../lib/strategyCatalog";
import { getDisplayTransactions } from "../lib/transactions";
import { won } from "../lib/validation";
import { useAuthStore } from "../store/authStore";
import { useInvestmentStore } from "../store/investmentStore";
import { useTradingStore } from "../store/tradingStore";
import PortfolioDataState from "../components/PortfolioDataState";
import { useTradingRetry } from "../hooks/useTradingRetry";
import type { Screen, TransactionRecord } from "../types";

interface Props {
  userName: string;
  /** App이 실제 GET /strategies에서 확인한 현재 전략과 전체 활성 카탈로그. */
  strategy: StrategyResponse;
  strategies: StrategyResponse[];
  onStrategyChange: (id: string) => void;
  onNavigate: (s: Screen) => void;
  onSelectStock: (stockCode: string) => void;
  onSelectTransaction: (id: string) => void;
  /** "더보기" — AI 손절·리밸런싱 제안 전체 목록(rebalance-alerts)으로 이동한다. onNavigate 대신 별도 prop을
   *  두는 이유는, 그 화면의 "돌아가기"가 진입 지점(Portfolio/PortfolioAuto 요약 위젯 vs 여기)에 따라
   *  달라져야 해서 App.tsx가 이동과 함께 back target을 같이 기록해야 하기 때문이다. */
  onOpenRebalanceAlerts: () => void;
  /** 모달의 "다시 진단하기" — 투자성향 진단으로 되돌린다 */
  onRediagnose: () => void;
  onAccountMissingAction?: () => void;
  /** 상단 "돌아가기" — PowerBI 컨테이너만 있는 `/portfolio` 로 되돌아간다 */
  onBack: () => void;
  isAutoMode: boolean;
}

/** 거래 유형별 배지 색 */
const TX_BADGE: Record<TransactionRecord["type"], string> = {
  매수: "bg-[#F4F6F1] text-[#3F4A43]",
  매도: "bg-[#EAF2FD] text-down",
  리밸런싱: "bg-[#FCF3E4] text-warn",
  배당: "bg-[#F8FCEE] text-[#3F5222]",
};

/** AI 제안 종류별 배지 색 — 보유 종목 테이블 배지 + AI 제안 카드 + 사유 모달이 공유한다 */
const ALERT_BADGE: Record<"손절" | "리밸런싱", string> = {
  손절: "bg-[#FBEAEA] text-up",
  리밸런싱: "bg-[#FCF3E4] text-warn",
};

const COMPARISON_PERIOD_LABEL: Record<PortfolioHistoryPeriod, string> = {
  "1M": "최근 1개월",
  "3M": "최근 3개월",
  "1Y": "최근 1년",
  ALL: "전체 기간",
};

/** GET /portfolio/comparison 응답 상태 — 두 계좌가 다 있어야 하고(없으면 accounts-required),
 *  공통 관측일이 부족하면(insufficient) 서버가 숫자를 만들어내지 않고 명시적으로 알려준다. */
type ComparisonState =
  | { kind: "loading" }
  | { kind: "accounts-required" }
  | { kind: "insufficient" }
  | { kind: "error" }
  | { kind: "ready"; data: PortfolioComparisonResponse };

/** `/portfolio/detail` — 실 계좌(useTradingStore) 데이터 기준 포트폴리오 관리 화면.
 *  PowerBI 차트(도넛/라인/바/레이더)는 `/portfolio`(Portfolio.tsx)에만 있고, 여기는 그 아래 실무 기능 전부:
 *  오늘의 스토리, 전략 설정, AI 손절·리밸런싱 제안(목업), 보유 종목, 거래 내역(실 체결), 자동매매 비교(실 API), 판단 회고(목업).
 *  매매 방식(반자동/전체자동) 토글은 백엔드에 그런 구분이 없어 넣지 않았다 — PR #57 에서도 같은 이유로 제거된 것으로 보인다. */
function PortfolioDetailContent({
  userName,
  strategy,
  strategies,
  onStrategyChange,
  onNavigate,
  onSelectStock,
  onSelectTransaction,
  onOpenRebalanceAlerts,
  onRediagnose,
  onBack,
  isAutoMode,
}: Props) {
  const token = useAuthStore((state) => state.accessToken);
  const logout = useAuthStore((state) => state.logout);
  const portfolio = useTradingStore((state) => state.portfolio);
  const executions = useTradingStore((state) => state.executions);
  // 계좌 자체가 없다고 "확인된" 상태(404) — 이 값만 mock 전환의 기준으로 쓴다. portfolio===null은
  // "계좌 없음"과 "계좌는 있는데 아직 로딩 중/조회 실패"를 구분하지 못해(둘 다 null) 기준으로 삼지 않는다.
  const accountMissing = useTradingStore((state) => state.accountMissing);
  const isLoading = useTradingStore((state) => state.isLoading);
  const error = useTradingStore((state) => state.error);

  const decisions = useTradingStore((state) => state.decisions);
  const account = useTradingStore((state) => state.account);
  const recordDecision = useTradingStore((state) => state.recordDecision);
  const isDecisionSubmitting = useTradingStore(
    (state) => state.isDecisionSubmitting,
  );
  const ensureAccount = useTradingStore((state) => state.ensureAccount);
  const activeMode = useInvestmentStore((state) => state.activeMode);
  const displayAlerts = useMemo(() => getDisplayAlerts(portfolio), [portfolio]);

  const displayDecisions: DisplayDecisionSummary = useMemo(
    () => getDisplayDecisions(decisions),
    [decisions],
  );

  // AI 자동투자 vs 내 투자 비교 — AUTO/SEMI_AUTO 두 계좌가 모두 있어야 하는 별도 API라 account_id가
  // 필요 없다(로그인 사용자 기준으로 백엔드가 알아서 두 계좌를 찾는다). 계좌가 하나뿐이면 409
  // COMPARISON_ACCOUNTS_REQUIRED로 실패하는데, 그것도 실제 상태라 mock으로 가리지 않고 그대로 안내한다.
  const [comparison, setComparison] = useState<ComparisonState>({
    kind: "loading",
  });
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setComparison({ kind: "loading" });
    getPortfolioComparisonApi("3M", token)
      .then((data) => {
        if (cancelled) return;
        setComparison(
          data.comparison_status === "AVAILABLE"
            ? { kind: "ready", data }
            : { kind: "insufficient" },
        );
      })
      .catch((e) => {
        if (cancelled) return;
        setComparison(
          e instanceof ApiError && e.code === "COMPARISON_ACCOUNTS_REQUIRED"
            ? { kind: "accounts-required" }
            : { kind: "error" },
        );
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // 전략 변경 모달 상태 — 현재 전략과 선택지는 모두 App의 실제 카탈로그를 사용한다.
  const [isModalOpen, setModalOpen] = useState(false);
  const setSelectedStrategy = async (nextStrategyId: string) => {
    if (!token) return;
    try {
      await ensureAccount(
        token,
        nextStrategyId,
        toAccountOperationMode(activeMode),
      );
      onStrategyChange(nextStrategyId);
      setModalOpen(false);
    } catch (requestError) {
      if ((requestError as { status?: number }).status === 401) void logout();
    }
  };

  // 페이지 내 서브뷰 전환 — 현재 앱은 URL 라우터가 없는 화면 상태 머신이라,
  // "지난 판단 돌아보기"는 실제 라우트(`/portfolio/review`) 대신 로컬 뷰 전환으로 구현한다.
  const [view, setView] = useState<"main" | "review">("main");

  // "왜 지금인가요?" — 보유 종목 배지를 누르면 여는 AI 제안 사유 모달. AI 제안 카드 자체는
  // "조정 제안/손절 조치 확인하기" 시트가 같은 내용(사유+조치)을 보여줘 중복이라 별도 버튼을 두지 않는다.
  const [alertModalId, setAlertModalId] = useState<string | null>(null);
  const alertModal = displayAlerts.find((a) => a.id === alertModalId) ?? null;

  // 총자산/보유종목 모두 계좌가 없다고 확인된 경우(accountMissing)에만 목업 값을 쓰고, 그 외(실 계좌
  // 포지션이 0개, 또는 아직 로딩 중/조회 실패로 portfolio를 못 받은 경우)에는 0원/빈 배열로 실제 빈
  // 상태를 보여준다 — portfolio===null 하나만으로 판단하면 "계좌 없음"과 "계좌는 있는데 로딩 중/조회
  // 실패"를 구분하지 못해, 로딩/오류 중에 실계좌 사용자에게 목업 데이터가 노출될 수 있다.
  // 실 포지션에는 investor-facing 메타(섹터/AI 편입 사유 등)가 없어 STOCK_INFO 코드로 목업과 매칭해 보완한다.
  const HOLD_TOTAL = Number(portfolio?.total_assets ?? 0);
  const ALL_HOLDINGS = useMemo(
    () => buildDetailedPortfolioHoldings(portfolio),
    [portfolio],
  );

  /** 오늘 손익 = 실 포지션이 있으면 평가손익(unrealized_profit), 없으면 평가금액×등락률(목업 근사) */
  const gains = useMemo(
    () =>
      ALL_HOLDINGS.map((h) => {
        const position = portfolio?.positions.find(
          (item) => item.stock_code === h.stockCode,
        );
        return {
          ...h,
          gain: position
            ? Number(position.unrealized_profit)
            : ((HOLD_TOTAL * h.pct) / 100) * ((h.chg ?? 0) / 100),
        };
      }),
    [ALL_HOLDINGS, HOLD_TOTAL, portfolio],
  );
  const todayTotal = gains.reduce((a, g) => a + g.gain, 0);
  // Dashboard.tsx 병합 — "오늘 무슨 일이 있었나요" 스토리 카드가 쓰는 오늘의 최고 기여 종목
  const top = useMemo(
    () => [...gains].sort((a, b) => b.gain - a.gain)[0],
    [gains],
  );

  // Dashboard.tsx 병합 — 리밸런싱 제안의 "조정 전/후" 상세 시트. AI_ALERTS 카드의 "조정 제안 확인하기"에서 연다.
  // 목표/현재 비중은 위 ALL_HOLDINGS(실 계좌 우선)를 그대로 써서, 실 계좌 상태와 숫자가 어긋나지 않게 한다.
  const [rebalanceSheetId, setRebalanceSheetId] = useState<string | null>(null);
  // 시트의 두 액션("조정하기"/"이번에는 하지 않을게요")이 실제로 다른 결과를 남기도록, 제안 id별로
  // 어떤 결정을 내렸는지 세션 동안 기억한다 — 백엔드에 실행 로직이 없는 목업이라 서버에 반영하진 않지만,
  // 카드/시트에 결정이 그대로 보여야 두 버튼이 "모달만 닫는 동일 동작"으로 보이지 않는다.
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const decisionKeys = useRef<Record<string, string>>({});
  const decisionFor = (alert: (typeof displayAlerts)[number]) => {
    const item = decisions?.items.find(
      (candidate) => candidate.proposal_key === alert.proposalKey,
    );
    return item?.decision === "ACCEPTED"
      ? "adjusted"
      : item
        ? "held"
        : undefined;
  };
  const rebalanceAlert =
    displayAlerts.find((a) => a.id === rebalanceSheetId) ?? null;
  const submitDecision = async (decision: "ACCEPTED" | "HELD") => {
    if (!rebalanceAlert || !account || !token || !rebalanceAlert.proposalKey)
      return;
    const key = `${rebalanceAlert.proposalKey}:${decision}`;
    const idempotencyKey = decisionKeys.current[key] ?? crypto.randomUUID();
    decisionKeys.current[key] = idempotencyKey;
    setDecisionError(null);
    try {
      await recordDecision(token, {
        account_id: account.id,
        stock_code:
          rebalanceAlert.stockCode ??
          rebalanceAlert.id.replace("rebalance-", ""),
        proposal_key: rebalanceAlert.proposalKey,
        decision,
        idempotency_key: idempotencyKey,
      });
      if (decision === "ACCEPTED") {
        if (strategy.id === "low") {
          await rebalanceLatestLossAvoidanceRecommendationApi(account.id, token);
        } else if (strategy.id === "momentum") {
          await rebalanceLatestModelRecommendationsApi(account.id, token);
        }
        await useTradingStore.getState().refresh(token, toAccountOperationMode(isAutoMode ? "auto" : "manual"));
      }
    } catch (error) {
      setDecisionError(
        error instanceof Error ? error.message : "판단을 저장하지 못했습니다.",
      );
    }
  };
  const rebalanceHolding = rebalanceAlert?.stockCode
    ? ALL_HOLDINGS.find((h) => h.stockCode === rebalanceAlert.stockCode)
    : undefined;
  // 실 제안이면 API가 이미 계산해 준 현재/목표 비중·조정금액을 그대로 쓴다 — 목업일 때만 보유 종목 목록에서
  // 같은 이름을 찾아(이름 매칭이라 실패할 수 있음) 대신 파생시킨다.
  const rebalanceCurrentPct =
    rebalanceAlert?.currentWeight ??
    (rebalanceHolding ? rebalanceHolding.pct : 0);
  const rebalanceTargetPct =
    rebalanceAlert?.targetWeight ??
    (rebalanceHolding ? (rebalanceHolding.target ?? rebalanceHolding.pct) : 0);
  const rebalanceAdjustAmount =
    rebalanceAlert?.recommendedAmount ??
    (rebalanceHolding
      ? Math.round(
          (HOLD_TOTAL * (rebalanceHolding.pct - rebalanceTargetPct)) / 100,
        )
      : 0);

  // 보유 종목 미리보기 — 비중이 큰 상위 5개만 보여주고, 전체 목록은 별도 페이지(/all-holdings)로 뺀다.
  const previewHoldings = useMemo(
    () => [...gains].sort((a, b) => b.pct - a.pct).slice(0, 5),
    [gains],
  );

  // 최근 거래 — 계좌가 없다고 확인된 경우에만 목업을 쓰고, 그 외(체결 0건, 로딩 중/조회 실패)에는
  // 실 체결 내역(빈 배열이어도)을 그대로 쓴다
  const displayTransactions = useMemo(
    () => getDisplayTransactions(executions),
    [executions],
  );

  if (view === "review") {
    return (
      <ReviewView
        userName={userName}
        onNavigate={onNavigate}
        onBack={() => setView("main")}
        decisions={displayDecisions}
      />
    );
  }

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col">
          {/* PowerBI Embedded 페이지(`/portfolio`)로 돌아가는 상단 네비게이션 */}
          <button
            onClick={onBack}
            className="mb-7 self-start text-[15px] text-muted"
          >
            ← 돌아가기
          </button>

          {/* ============ 오늘: 인사말/총자산 + 오늘의 스토리 ============ */}
          <section className="flex flex-col gap-7">
            <div className="flex flex-col gap-4">
              <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
                {userName}님의 투자는
                <br />
                오늘도 전략대로 움직이고 있어요.
              </h1>
              <div className="flex items-baseline gap-4">
                <span className="text-[40px] font-bold tracking-[-0.035em]">
                  {won(HOLD_TOTAL)}
                </span>
                <span className="text-xl font-bold text-up">
                  오늘 {todayTotal >= 0 ? "+" : ""}
                  {Math.round(todayTotal).toLocaleString("ko-KR")}원
                </span>
              </div>
            </div>

            {/* Dashboard.tsx 병합 — "오늘 무슨 일이 있었나요" 스토리 카드. 짧은 인사이트 2장이라
                세로로 쌓지 않고 나란히 둬서 한눈에 훑을 수 있게 한다. */}
            <div className="flex flex-col gap-3.5">
              <h2 className="text-[15px] font-semibold text-muted">
                오늘 내 투자에는 무슨 일이 있었나요
              </h2>
              <div className="grid grid-cols-2 gap-4">
                {top ? (
                  <Story
                    title={`${top.name}가 오늘 수익을 가장 많이 만들었어요`}
                  >
                    <div className="flex items-baseline gap-3">
                      <span className="text-xl font-bold text-up">
                        +{Math.round(top.gain).toLocaleString("ko-KR")}원
                      </span>
                      <span className="text-sm text-muted">
                        오늘 전체 수익의{" "}
                        {todayTotal !== 0
                          ? Math.round((top.gain / todayTotal) * 100)
                          : 0}
                        %
                      </span>
                    </div>
                  </Story>
                ) : (
                  <Story title="아직 보유 중인 종목이 없어요">
                    <span className="text-sm leading-6 text-muted">
                      계좌에 입금하고 투자를 시작하면 여기에 오늘의 이야기가
                      채워져요.
                    </span>
                  </Story>
                )}
                {/* 보유 종목이 없으면(top === undefined) 이 카드도 고정 mock 스토리를 보여주지 않는다 —
                    바로 위 카드가 이미 "아직 보유 중인 종목이 없어요"로 빈 상태를 알려주는데, 그 아래에
                    실제로는 없는 KT&G 보유를 전제한 문구가 이어지면 모순된다. */}
                {top && (
                  <Story title="KT&G는 포트폴리오의 흔들림을 줄여줬어요">
                    <span className="text-sm leading-6 text-muted">
                      오늘 시장보다 변동성이 낮았어요.
                    </span>
                  </Story>
                )}
              </div>
            </div>
          </section>

          {/* ============ 전략: 슬림 스트립 — 텍스트 몇 줄짜리 설정 항목이라 큰 카드 대신 얇은 줄로 둔다 ============ */}
          <section className="mt-10 flex items-center justify-between gap-6 rounded-panel bg-surface px-8 py-5">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-[13px] text-subtle">현재 전략</span>
              <span className="text-lg font-bold tracking-[-0.02em]">
                {strategy.name}
              </span>
              <span className="text-[13px] text-muted">
                · 위험도 {strategyRiskLabel(strategy.risk_level)} · 리밸런싱{" "}
                {strategyRebalanceLabel(strategy.rebalance_cycle)}
              </span>
            </div>
            <button
              onClick={() => setModalOpen(true)}
              className="shrink-0 rounded-field bg-[#F4F6F1] px-5 py-2.5 text-sm font-semibold text-[#3F4A43]"
            >
              전략 변경하기
            </button>
          </section>

          {/* ============ 내 자산: 보유 종목 + 최근 거래 — 둘 다 "무엇을 갖고 있는지" 리스트라 나란히 둔다 ============ */}
          <section className="mt-14 flex flex-col gap-4">
            <h2 className="text-[15px] font-semibold text-muted">내 자산</h2>
            <div className="grid grid-cols-2 gap-5">
              {/* 보유 종목 미리보기 — 비중 상위 5종목만 보여주고 전체 목록은 /all-holdings 로 뺀다.
                  투자 원금/수익률은 실 계좌 포지션(purchase_amount/return_rate)이 있으면 그 값을, 없으면 목업 값을 쓴다. */}
              <div className="flex flex-col gap-3 rounded-card bg-surface p-7">
                <div className="flex items-baseline justify-between">
                  <h2 className="text-xl font-bold tracking-[-0.02em]">
                    보유 종목
                  </h2>
                  <button
                    onClick={() => onNavigate("all-holdings")}
                    className="text-sm font-semibold text-navy"
                  >
                    전체 종목 보기 →
                  </button>
                </div>
                <div className="flex flex-col">
                  {previewHoldings.length === 0 && (
                    <p className="py-6 text-center text-[15px] text-subtle">
                      아직 보유 중인 종목이 없어요.
                    </p>
                  )}
                  {previewHoldings.map((h) => {
                    const stockCode = h.stockCode;
                    const alert = displayAlerts.find(
                      (a) => a.stockCode === stockCode,
                    );
                    return (
                      <button
                        key={h.stockCode}
                        onClick={() => stockCode && onSelectStock(stockCode)}
                        className="flex items-center gap-4 border-t border-line py-3.5 text-left first:border-0 hover:bg-canvas"
                      >
                        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                          <div className="flex items-center gap-2">
                            <span className="truncate text-[15px] font-semibold tracking-[-0.01em]">
                              {h.name}
                            </span>
                            {alert && (
                              <span
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setAlertModalId(alert.id);
                                }}
                                className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ${ALERT_BADGE[alert.kind]}`}
                              >
                                {alert.badge}
                              </span>
                            )}
                          </div>
                          <span className="text-xs text-subtle">
                            {h.sector}
                          </span>
                        </div>
                        <span className="w-14 shrink-0 text-right text-sm font-bold">
                          {h.pct.toFixed(1)}%
                        </span>
                        <span
                          className={`w-16 shrink-0 text-right text-[13px] font-semibold ${
                            (h.returnRate ?? 0) > 0
                              ? "text-up"
                              : (h.returnRate ?? 0) < 0
                                ? "text-down"
                                : "text-subtle"
                          }`}
                        >
                          {(h.returnRate ?? 0) > 0 ? "+" : ""}
                          {(h.returnRate ?? 0).toFixed(1)}%
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* 최근 거래 — 실 체결 내역이 있으면 최신 3건, 없으면 목업 3건. 전체 내역은 별도 페이지로 라우팅한다 */}
              <div className="flex flex-col gap-3 rounded-card bg-surface p-7">
                <div className="flex items-baseline justify-between">
                  <h2 className="text-xl font-bold tracking-[-0.02em]">
                    최근 거래
                  </h2>
                  <button
                    onClick={() => onNavigate("transactions")}
                    className="text-sm font-semibold text-navy"
                  >
                    더보기 →
                  </button>
                </div>
                <div className="flex flex-col">
                  {displayTransactions.length === 0 && (
                    <p className="py-6 text-center text-[15px] text-subtle">
                      아직 거래 내역이 없어요.
                    </p>
                  )}
                  {displayTransactions.slice(0, 3).map((t) => (
                    <button
                      key={t.id}
                      onClick={() => onSelectTransaction(t.id)}
                      className="flex items-center gap-3.5 border-t border-line py-3.5 text-left first:border-0 hover:bg-canvas"
                    >
                      <span className="w-14 shrink-0 text-xs text-subtle">
                        {t.date.slice(5)}
                      </span>
                      <span
                        className={`shrink-0 rounded-full px-2.5 py-1 text-center text-[11px] font-bold ${TX_BADGE[t.type]}`}
                      >
                        {t.type}
                      </span>
                      <span className="flex-1 truncate text-[15px] font-semibold text-[#3F4A43]">
                        {t.stockName}
                      </span>
                      <span
                        className={`shrink-0 text-sm font-bold ${t.amount >= 0 ? "text-up" : "text-down"}`}
                      >
                        {t.amount >= 0 ? "+" : ""}
                        {t.amount.toLocaleString("ko-KR")}원
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* ============ AI 인사이트: 리밸런싱 제안 + AI vs 나 비교 + 판단 회고 — 전부 "AI가 내 투자를
              어떻게 보고 있는지"라 하나의 구역으로 묶는다 ============ */}
          <section className="mt-14 flex flex-col gap-4">
            <h2 className="text-[15px] font-bold text-[#3F5222]">
              ✦ AI 인사이트
            </h2>

            {/* AI 손절/리밸런싱 제안 — 실 계좌에 제안이 있으면 그 값을, 없으면 목업을 쓴다(lib/rebalancing.ts).
                "조정 제안/손절 조치 확인하기"를 누르면 사유+조치 시트가 열린다 */}
            {displayAlerts.length > 0 && (
              <div className="flex flex-col gap-5 rounded-card bg-surface p-7">
                <div className="flex items-baseline justify-between gap-4">
                  <h2 className="text-xl font-bold tracking-[-0.02em]">
                    지금 확인해야 할 손절·리밸런싱 제안이 있어요
                  </h2>
                  <button
                    onClick={onOpenRebalanceAlerts}
                    className="shrink-0 text-sm font-semibold text-navy"
                  >
                    더보기 →
                  </button>
                </div>
                <div className="flex flex-col gap-3">
                  {displayAlerts.slice(0, 3).map((a) => {
                    const decision = decisionFor(a);
                    return (
                      <div
                        key={a.id}
                        className="flex items-center justify-between gap-5 rounded-[18px] bg-canvas px-6 py-5"
                      >
                        <div className="flex min-w-0 flex-col gap-1.5">
                          <div className="flex items-center gap-2">
                            <span
                              className={`rounded-full px-2.5 py-1 text-xs font-bold ${ALERT_BADGE[a.kind]}`}
                            >
                              {a.badge}
                            </span>
                            <span className="text-base font-bold tracking-[-0.02em]">
                              {a.stockName}
                            </span>
                            {decision && (
                              <span
                                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold ${
                                  decision === "adjusted"
                                    ? "bg-[#F8FCEE] text-[#3F5222]"
                                    : "bg-[#F4F6F1] text-muted"
                                }`}
                              >
                                {decision === "adjusted"
                                  ? "✓ 승인함"
                                  : "보류함"}
                              </span>
                            )}
                          </div>
                          <p className="truncate text-sm text-muted">
                            {a.headline}
                          </p>
                        </div>
                        <button
                          onClick={() => setRebalanceSheetId(a.id)}
                          className={`shrink-0 rounded-field px-5 py-3 text-sm font-bold ${
                            decision
                              ? "bg-[#F4F6F1] text-[#3F4A43]"
                              : "bg-lime text-navy"
                          }`}
                        >
                          {decision
                            ? "결정 다시 보기"
                            : a.kind === "리밸런싱"
                              ? "조정 제안 확인하기"
                              : "손절 조치 확인하기"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-5">
              {/* AI 자동투자 vs 내 투자 — GET /portfolio/comparison(실 API). AUTO/SEMI_AUTO 계좌가 둘 다
                  있어야 비교가 가능하고, 공통 관측일이 부족하면 서버가 숫자를 만들지 않고 그대로 알려준다. */}
              <div className="flex flex-col gap-4 rounded-card bg-surface p-7">
                <div className="flex flex-col gap-1">
                  <h2 className="text-lg font-bold tracking-[-0.02em]">
                    AI 자동투자 vs 내 투자
                  </h2>
                  {comparison.kind === "ready" && (
                    <p className="text-xs text-muted">
                      {COMPARISON_PERIOD_LABEL[comparison.data.period]} 동안의
                      두 운용방식 성과예요.
                    </p>
                  )}
                </div>

                {comparison.kind === "loading" && (
                  <p className="text-sm text-subtle">
                    비교 정보를 불러오는 중이에요.
                  </p>
                )}
                {comparison.kind === "accounts-required" && (
                  <p className="text-sm text-subtle">
                    자동투자와 반자동 계좌가 모두 있어야 비교할 수 있어요. 아직
                    한쪽 운용방식만 이용 중이에요.
                  </p>
                )}
                {comparison.kind === "insufficient" && (
                  <p className="text-sm text-subtle">
                    두 계좌가 함께 운용된 기간이 아직 짧아 비교할 데이터가
                    충분하지 않아요.
                  </p>
                )}
                {comparison.kind === "error" && (
                  <p className="text-sm text-subtle">
                    비교 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.
                  </p>
                )}

                {comparison.kind === "ready" &&
                  (() => {
                    const { accounts, metrics, ai_analysis } = comparison.data;
                    const aiReturn =
                      accounts.ai_auto.return_rate == null
                        ? null
                        : Number(accounts.ai_auto.return_rate);
                    const myReturn =
                      accounts.my_investment.return_rate == null
                        ? null
                        : Number(accounts.my_investment.return_rate);
                    return (
                      <>
                        <div className="grid grid-cols-2 gap-3">
                          <div className="flex flex-col gap-1.5 rounded-[18px] bg-canvas px-5 py-4">
                            <span className="text-xs text-muted">
                              AI 자동투자
                            </span>
                            <span
                              className={`text-xl font-bold tracking-[-0.02em] ${
                                aiReturn == null
                                  ? "text-subtle"
                                  : aiReturn >= 0
                                    ? "text-up"
                                    : "text-down"
                              }`}
                            >
                              {aiReturn == null
                                ? "데이터 없음"
                                : `${aiReturn >= 0 ? "+" : ""}${aiReturn.toFixed(2)}%`}
                            </span>
                          </div>
                          <div className="flex flex-col gap-1.5 rounded-[18px] bg-canvas px-5 py-4">
                            <span className="text-xs text-muted">
                              내 투자 (반자동)
                            </span>
                            <span
                              className={`text-xl font-bold tracking-[-0.02em] ${
                                myReturn == null
                                  ? "text-subtle"
                                  : myReturn >= 0
                                    ? "text-up"
                                    : "text-down"
                              }`}
                            >
                              {myReturn == null
                                ? "데이터 없음"
                                : `${myReturn >= 0 ? "+" : ""}${myReturn.toFixed(2)}%`}
                            </span>
                          </div>
                        </div>
                        <Insight compact>
                          {ai_analysis.status === "AVAILABLE" &&
                          (ai_analysis.headline ?? ai_analysis.summary)
                            ? (ai_analysis.headline ?? ai_analysis.summary)
                            : metrics
                              ? metrics.leader === "TIE"
                                ? "이 기간에는 두 방식의 성과가 비슷해요."
                                : `이 기간에는 ${metrics.leader === "AI_AUTO" ? "AI 자동투자" : "내 투자"}가 ${Math.abs(Number(metrics.return_rate_gap)).toFixed(1)}%p 더 좋았어요.`
                              : "비교할 수 있는 결과가 아직 없어요."}
                        </Insight>
                        {ai_analysis.status === "AVAILABLE" &&
                          ai_analysis.caution && (
                            <p className="text-xs text-subtle">
                              ※ {ai_analysis.caution}
                            </p>
                          )}
                      </>
                    );
                  })()}
              </div>

              {/* "내 투자 판단은 어땠을까요?" — 요약 카드. 상세 회고는 "지난 판단 돌아보기"에서 서브뷰로 전환한다.
                  실 계좌에 리밸런싱 판단 이력이 있으면 그 값을, 없으면 목업을 쓴다(lib/decisions.ts). */}
              <div className="flex flex-col gap-4 rounded-card bg-surface p-7">
                <h2 className="text-lg font-bold tracking-[-0.02em]">
                  내 투자 판단은 어땠을까요
                </h2>
                {displayDecisions.items.length > 0 && (
                  <>
                    <div className="flex flex-col gap-1.5">
                      <span className="text-xs text-subtle">
                        지난 리밸런싱 제안
                      </span>
                      <div className="flex flex-wrap items-center gap-2 text-sm text-[#3F4A43]">
                        <span>
                          AI 제안 <b>{displayDecisions.items[0].action}</b>
                        </span>
                        <span className="text-[#A6AFA7]">·</span>
                        <span>
                          내 선택{" "}
                          <b>
                            {displayDecisions.items[0].choice === "수락"
                              ? "수락함"
                              : "하지 않음 (보류)"}
                          </b>
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1.5 rounded-[18px] bg-canvas px-5 py-4">
                      <span className="text-xs text-muted">결과</span>
                      <span className="text-lg font-bold tracking-[-0.02em]">
                        {displayDecisions.items[0].result}
                      </span>
                    </div>
                  </>
                )}
                <button
                  onClick={() => setView("review")}
                  className="self-start text-sm font-semibold text-navy"
                >
                  지난 판단 돌아보기 →
                </button>
              </div>
            </div>
          </section>
        </div>
      </main>

      {/* 전략 변경 모달 — 현재 전략만 라임 테두리로 강조 */}
      {isModalOpen && (
        <div
          className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8"
          onClick={() => setModalOpen(false)}
        >
          <div
            className="flex w-[640px] flex-col gap-7 rounded-card bg-surface p-12"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-6">
              <div className="flex flex-col gap-2.5">
                <h2 className="text-[28px] font-bold tracking-[-0.03em]">
                  어떤 전략으로 운용할까요?
                </h2>
                <p className="text-[17px] leading-7 text-muted">
                  전략은 언제든 바꿀 수 있어요.
                </p>
              </div>
              <button
                aria-label="닫기"
                onClick={() => setModalOpen(false)}
                className="rounded-[9px] bg-canvas p-2 text-muted"
              >
                <X size={18} />
              </button>
            </div>

            <div className="flex flex-col gap-3">
              {strategies.map((s) => {
                const active = s.id === strategy.id;
                return (
                  <button
                    key={s.id}
                    onClick={() => void setSelectedStrategy(s.id)}
                    className={`flex items-center justify-between rounded-[20px] px-8 py-7 text-left ${
                      active
                        ? "bg-[#F8FCEE] shadow-[0_0_0_2px_#C6F04D_inset]"
                        : "bg-canvas shadow-[0_0_0_1px_#E5E9E3_inset]"
                    }`}
                  >
                    <span className="text-[22px] font-bold tracking-[-0.02em]">
                      {s.name}
                    </span>
                    {active && (
                      <span className="rounded-full bg-lime px-3.5 py-2 text-sm font-bold text-navy">
                        현재 전략
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            <button
              onClick={onRediagnose}
              className="rounded-field bg-[#F4F6F1] py-5 text-[17px] font-semibold text-[#3F4A43]"
            >
              다시 진단하기
            </button>
          </div>
        </div>
      )}

      {/* AI 제안 사유 모달 — "왜 지금인가요?" 클릭 시 근거와 제안 조치를 보여준다 */}
      {alertModal && (
        <div
          className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8"
          onClick={() => setAlertModalId(null)}
        >
          <div
            className="flex w-[560px] flex-col gap-6 rounded-card bg-surface p-11"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-6">
              <div className="flex flex-col gap-2.5">
                <span
                  className={`w-fit rounded-full px-3 py-1.5 text-sm font-bold ${ALERT_BADGE[alertModal.kind]}`}
                >
                  {alertModal.badge}
                </span>
                <h2 className="text-[24px] font-bold tracking-[-0.025em]">
                  {alertModal.stockName} · 왜 지금인가요?
                </h2>
              </div>
              <button
                aria-label="닫기"
                onClick={() => setAlertModalId(null)}
                className="rounded-[9px] bg-canvas p-2 text-muted"
              >
                <X size={18} />
              </button>
            </div>
            <p className="text-[17px] leading-7 text-[#3F4A43]">
              {alertModal.reason}
            </p>
            <div className="flex items-center gap-3 rounded-[16px] bg-[#F8FCEE] px-7 py-6">
              <span className="shrink-0 text-[15px] font-semibold text-[#3F5222]">
                AI 제안
              </span>
              <span className="text-[16px] font-semibold text-ink">
                {alertModal.action}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Dashboard.tsx 병합 — 리밸런싱 "조정 전/후" 상세 시트. 손절 제안은 목표 비중 개념이 없어
          같은 시트에서 "현재→조정후" 비교 대신 AI 제안 액션을 보여준다. "조정 제안/손절 조치 확인하기" 클릭 시 연다. */}
      {rebalanceAlert && (
        <div
          className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8"
          onClick={() => setRebalanceSheetId(null)}
        >
          <div
            className="flex w-[720px] flex-col gap-7 rounded-card bg-surface p-12"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-6">
              <h2 className="text-[28px] font-bold leading-10 tracking-[-0.03em]">
                {rebalanceAlert.kind === "리밸런싱"
                  ? "왜 지금 비중을 조정하라고 하나요?"
                  : "왜 지금 정리하는 게 좋을까요?"}
              </h2>
              <button
                aria-label="닫기"
                onClick={() => setRebalanceSheetId(null)}
                className="rounded-[9px] bg-canvas p-2 text-muted"
              >
                <X size={18} />
              </button>
            </div>
            <p className="text-lg leading-[30px] text-[#3F4A43]">
              {rebalanceAlert.reason}
            </p>
            {rebalanceAlert.kind === "리밸런싱" ? (
              <div className="flex items-center gap-6 rounded-[18px] bg-canvas px-8 py-7">
                <div className="flex flex-1 flex-col gap-2">
                  <span className="text-[15px] text-muted">현재</span>
                  <span className="text-[28px] font-bold tracking-[-0.03em] text-warn">
                    {rebalanceCurrentPct.toFixed(1)}%
                  </span>
                  <div className="h-2.5 rounded-full bg-[#E5E9E3]">
                    <div
                      className="h-2.5 rounded-full bg-warn"
                      style={{ width: `${rebalanceCurrentPct}%` }}
                    />
                  </div>
                </div>
                <span className="text-2xl text-[#A6AFA7]">→</span>
                <div className="flex flex-1 flex-col gap-2">
                  <span className="text-[15px] text-muted">조정 후</span>
                  <span className="text-[28px] font-bold tracking-[-0.03em]">
                    {rebalanceTargetPct.toFixed(1)}%
                  </span>
                  <div className="h-2.5 rounded-full bg-[#E5E9E3]">
                    <div
                      className="h-2.5 rounded-full bg-navy"
                      style={{ width: `${rebalanceTargetPct}%` }}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 rounded-[18px] bg-canvas px-8 py-7">
                <span className="shrink-0 text-[15px] font-semibold text-[#3F5222]">
                  AI 제안
                </span>
                <span className="text-[17px] font-semibold text-ink">
                  {rebalanceAlert.action}
                </span>
              </div>
            )}
            <div className="flex flex-col gap-2.5 rounded-[18px] bg-[#F8FCEE] px-8 py-7">
              <span className="text-lg font-bold tracking-[-0.02em]">
                {rebalanceAlert.kind === "리밸런싱"
                  ? "조정하지 않으면?"
                  : "정리하지 않으면?"}
              </span>
              <p className="text-[17px] leading-7 text-[#3F4A43]">
                특정 종목의 영향이 커져 {strategy.name}보다 포트폴리오가 더 많이
                흔들릴 수 있어요.
              </p>
            </div>
            {decisionFor(rebalanceAlert) ? (
              <div className="flex items-center gap-4 rounded-[18px] bg-[#F4F6F1] px-8 py-7">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-lime text-navy">
                  <Check size={18} />
                </span>
                <div className="flex flex-1 flex-col gap-1">
                  <span className="text-[17px] font-bold text-ink">
                    {decisionFor(rebalanceAlert) === "adjusted"
                      ? "이 제안을 승인했어요"
                      : "이번엔 보류했어요"}
                  </span>
                  <span className="text-[15px] text-muted">
                    {decisionFor(rebalanceAlert) === "adjusted"
                      ? "AI가 다음 리밸런싱에 반영해요."
                      : "다음에 다시 확인할 수 있어요."}
                  </span>
                </div>
                <button
                  onClick={() => setRebalanceSheetId(null)}
                  className="shrink-0 rounded-field bg-navy px-6 py-3.5 text-[15px] font-bold text-white"
                >
                  닫기
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {decisionError && (
                  <p role="alert" className="text-sm font-semibold text-up">
                    {decisionError}
                  </p>
                )}
                <div className="flex gap-3">
                  <button
                    disabled={isDecisionSubmitting}
                    onClick={() => void submitDecision("ACCEPTED")}
                    className="flex-1 rounded-field bg-lime py-5 text-lg font-bold text-navy"
                  >
                    {rebalanceAlert.kind === "리밸런싱"
                      ? `${won(Math.abs(rebalanceAdjustAmount))} 조정하기`
                      : "제안대로 정리하기"}
                  </button>
                  <button
                    disabled={isDecisionSubmitting}
                    onClick={() => void submitDecision("HELD")}
                    className="rounded-field bg-[#F4F6F1] px-8 py-5 text-[17px] font-semibold text-[#3F4A43] disabled:opacity-50"
                  >
                    이번에는 하지 않을게요
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function PortfolioDetail(props: Props) {
  useTradingData();
  const loading = useTradingStore((state) => state.isLoading);
  const accountMissing = useTradingStore((state) => state.accountMissing);
  const error = useTradingStore((state) => state.error);
  const retry = useTradingRetry();
  if (loading || accountMissing || error) {
    return (
      <PortfolioDataState
        userName={props.userName}
        onNavigate={props.onNavigate}
        loading={loading}
        accountMissing={accountMissing}
        error={error}
        onRetry={retry}
        onAccountMissingAction={props.onAccountMissingAction}
      >
        <div />
      </PortfolioDataState>
    );
  }
  return <PortfolioDetailContent {...props} />;
}

/** PDF Page 5 — "내 투자 판단 돌아보기" 서브뷰. 라우터가 생기면 `/portfolio/review` 로 그대로 옮길 수 있다.
 *  변동성 비교(AI 제안을 따랐을 때 vs 실제 선택)는 실 API에 그 개념 자체가 없어(수익률만 제공) 뺐다 —
 *  리밸런싱 모델이 그런 지표를 내려주기 시작하면 다시 넣을 수 있다. */
function ReviewView({
  userName,
  onNavigate,
  onBack,
  decisions,
}: {
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
  decisions: DisplayDecisionSummary;
}) {
  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <button
            onClick={onBack}
            className="self-start text-[15px] text-muted"
          >
            ← 포트폴리오 대시보드로 돌아가기
          </button>

          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">
              투자 판단 기록
            </span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
              내 투자 판단 돌아보기
            </h1>
            <p className="text-[19px] leading-8 text-muted">
              AI 제안과 내가 내린 선택이 이후 포트폴리오에 어떤 차이를
              만들었는지 살펴볼 수 있어요.
            </p>
          </section>

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex items-center justify-between">
              <h2 className="text-[22px] font-bold tracking-[-0.025em]">
                요약 통계
              </h2>
              <span className="rounded-full bg-[#F4F6F1] px-4 py-2 text-sm font-semibold text-[#3F4A43]">
                {decisions.periodLabel}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-8">
              <Stat label="AI 제안" value={`${decisions.proposed}회`} />
              <Stat label="수락" value={`${decisions.accepted}회`} />
              <Stat label="보류" value={`${decisions.held}회`} />
            </div>
          </section>

          <section className="flex flex-col gap-5 rounded-card bg-surface p-12">
            <div className="flex items-baseline justify-between">
              <h2 className="text-[22px] font-bold tracking-[-0.025em]">
                최근 판단 기록
              </h2>
              <span className="text-[15px] text-subtle">
                최근 {decisions.items.length}건
              </span>
            </div>
            <div className="flex flex-col">
              {decisions.items.length === 0 ? (
                <p className="py-10 text-center text-[15px] text-subtle">
                  아직 판단 기록이 없어요.
                </p>
              ) : (
                decisions.items.map((d) => (
                  <div
                    key={d.id}
                    className="flex items-center gap-6 border-b border-line py-5 last:border-0"
                  >
                    <span className="w-24 shrink-0 text-[14px] text-subtle">
                      {d.date}
                    </span>
                    <span className="flex-1 text-[17px] font-semibold text-[#3F4A43]">
                      {d.action}
                    </span>
                    <span
                      className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-bold ${
                        d.choice === "수락"
                          ? "bg-[#EAF7EF] text-[#2E9B65]"
                          : "bg-[#F4F6F1] text-muted"
                      }`}
                    >
                      ● {d.choice}
                    </span>
                    <span className="w-48 shrink-0 text-right text-[15px] text-muted">
                      {d.result}
                    </span>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

/** Dashboard.tsx 병합 — "오늘 무슨 일이 있었나요" 스토리 카드 껍데기 */
function Story({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-card bg-surface p-7">
      <span className="text-lg font-bold leading-[26px] tracking-[-0.02em]">
        {title}
      </span>
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[15px] text-muted">{label}</span>
      <span className="text-[32px] font-bold tracking-[-0.03em]">{value}</span>
    </div>
  );
}

function Insight({
  children,
  compact,
}: {
  children: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <div
      className={`flex items-start gap-4 rounded-[18px] bg-[#F8FCEE] ${compact ? "px-5 py-4" : "px-8 py-6"}`}
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-lime text-base text-navy">
        ✦
      </div>
      <p
        className={`pt-0.5 text-[#3F4A43] ${compact ? "text-sm leading-6" : "text-[17px] leading-7"}`}
      >
        {children}
      </p>
    </div>
  );
}
