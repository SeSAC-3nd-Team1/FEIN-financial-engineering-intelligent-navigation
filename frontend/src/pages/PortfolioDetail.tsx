import { useMemo, useState } from 'react';
import { ChevronDown, ChevronsUpDown, ChevronUp, X } from 'lucide-react';
import Header from '../components/Header';
import {
  AI_ALERTS, ALL_HOLDINGS as MOCK_HOLDINGS, AUTO_VS_MANUAL, DECISION_SUMMARY,
  HOLD_TOTAL as MOCK_HOLD_TOTAL, PAST_DECISIONS, STOCK_INFO,
} from '../data/holdings';
import { STRATEGIES } from '../data/strategies';
import { useTradingData } from '../hooks/useTradingData';
import { getDisplayTransactions } from '../lib/transactions';
import { won } from '../lib/validation';
import { useAuthStore } from '../store/authStore';
import { useTradingStore } from '../store/tradingStore';
import type { Screen, TransactionRecord } from '../types';

interface Props {
  userName: string;
  /** 모달에서 선택·표시되는 현재 전략 id — RiskResult/StrategyDetail 과 동일한 STRATEGIES.id 를 그대로 쓴다 */
  strategyId: string;
  onStrategyChange: (id: string) => void;
  onNavigate: (s: Screen) => void;
  onSelectStock: (index: number) => void;
  onSelectTransaction: (id: string) => void;
  /** 모달의 "다시 진단하기" — 투자성향 진단으로 되돌린다 */
  onRediagnose: () => void;
  /** 상단 "돌아가기" — PowerBI 컨테이너만 있는 `/portfolio` 로 되돌아간다 */
  onBack: () => void;
}

/** 거래 유형별 배지 색 */
const TX_BADGE: Record<TransactionRecord['type'], string> = {
  '매수': 'bg-[#F4F6F1] text-[#3F4A43]',
  '매도': 'bg-[#EAF2FD] text-down',
  '리밸런싱': 'bg-[#FCF3E4] text-warn',
  '배당': 'bg-[#F8FCEE] text-[#3F5222]',
};

/** AI 제안 종류별 배지 색 — 보유 종목 테이블 배지 + AI 제안 카드 + 사유 모달이 공유한다 */
const ALERT_BADGE: Record<'손절' | '리밸런싱', string> = {
  '손절': 'bg-[#FBEAEA] text-up',
  '리밸런싱': 'bg-[#FCF3E4] text-warn',
};

/** 보유 종목 테이블 — 클릭으로 오름/내림차순 토글되는 정렬 열 */
type SortKey = 'name' | 'pct' | 'principal' | 'returnRate';
const HOLDINGS_COLUMNS: { key: SortKey; label: string; align: 'left' | 'right' }[] = [
  { key: 'name', label: '종목명', align: 'left' },
  { key: 'pct', label: '비율', align: 'right' },
  { key: 'principal', label: '투자 원금', align: 'right' },
  { key: 'returnRate', label: '원금 대비 수익률', align: 'right' },
];

/** `/portfolio/detail` — 실 계좌(useTradingStore) 데이터 기준 포트폴리오 관리 화면.
 *  PowerBI 차트(도넛/라인/바/레이더)는 `/portfolio`(Portfolio.tsx)에만 있고, 여기는 그 아래 실무 기능 전부:
 *  오늘의 스토리, 전략 설정, AI 손절·리밸런싱 제안(목업), 보유 종목, 거래 내역(실 체결), 자동매매 비교(목업), 판단 회고(목업).
 *  매매 방식(반자동/전체자동) 토글은 백엔드에 그런 구분이 없어 넣지 않았다 — PR #57 에서도 같은 이유로 제거된 것으로 보인다. */
export default function PortfolioDetail({
  userName, strategyId, onStrategyChange, onNavigate, onSelectStock, onSelectTransaction, onRediagnose, onBack,
}: Props) {
  const token = useTradingData();
  const logout = useAuthStore((state) => state.logout);
  const portfolio = useTradingStore((state) => state.portfolio);
  const executions = useTradingStore((state) => state.executions);
  const ensureAccount = useTradingStore((state) => state.ensureAccount);

  // 전략 변경 모달 상태
  const [isModalOpen, setModalOpen] = useState(false);
  // strategyId 로부터 표시용 전략 객체(이름/나와 맞는 정도 등)를 파생시킨다 — STRATEGIES 가 유일한 출처
  const selectedStrategy = STRATEGIES.find((s) => s.id === strategyId) ?? STRATEGIES[0];
  const setSelectedStrategy = async (nextStrategyId: string) => {
    if (!token) return;
    try {
      await ensureAccount(token, nextStrategyId);
      onStrategyChange(nextStrategyId);
      setModalOpen(false);
    } catch (requestError) {
      if ((requestError as { status?: number }).status === 401) void logout();
    }
  };

  // 페이지 내 서브뷰 전환 — 현재 앱은 URL 라우터가 없는 화면 상태 머신이라,
  // "지난 판단 돌아보기"는 실제 라우트(`/portfolio/review`) 대신 로컬 뷰 전환으로 구현한다.
  const [view, setView] = useState<'main' | 'review'>('main');

  // "왜 지금인가요?" — AI 손절/리밸런싱 제안 사유 모달. 카드와 보유 종목 배지가 같은 상태를 공유한다.
  const [alertModalId, setAlertModalId] = useState<string | null>(null);
  const alertModal = AI_ALERTS.find((a) => a.id === alertModalId) ?? null;

  // 보유 종목 테이블 정렬 상태 — 헤더 클릭 시 같은 열이면 방향 토글, 다른 열이면 내림차순으로 새로 시작
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
  };

  // 실 계좌가 있으면 포지션을, 없으면 목업 20종목을 쓴다 — Portfolio.tsx(PowerBI)와 동일한 대체 규칙.
  // 실 포지션에는 investor-facing 메타(섹터/AI 편입 사유 등)가 없어 STOCK_INFO 코드로 목업과 매칭해 보완한다.
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

  /** 오늘 손익 = 실 포지션이 있으면 평가손익(unrealized_profit), 없으면 평가금액×등락률(목업 근사) */
  const gains = useMemo(
    () => ALL_HOLDINGS.map((h) => {
      const code = STOCK_INFO[h.name]?.code;
      const position = portfolio?.positions.find((item) => item.stock_code === code);
      return {
        ...h,
        gain: position
          ? Number(position.unrealized_profit)
          : (HOLD_TOTAL * h.pct) / 100 * (h.chg / 100),
      };
    }),
    [ALL_HOLDINGS, HOLD_TOTAL, portfolio]
  );
  const todayTotal = gains.reduce((a, g) => a + g.gain, 0);
  // Dashboard.tsx 병합 — "오늘 무슨 일이 있었나요" 스토리 카드가 쓰는 오늘의 최고 기여 종목
  const top = useMemo(() => [...gains].sort((a, b) => b.gain - a.gain)[0], [gains]);

  // Dashboard.tsx 병합 — 리밸런싱 제안의 "조정 전/후" 상세 시트. AI_ALERTS 카드의 "조정 제안 확인하기"에서 연다.
  // 목표/현재 비중은 위 ALL_HOLDINGS(실 계좌 우선)를 그대로 써서, 실 계좌 상태와 숫자가 어긋나지 않게 한다.
  const [rebalanceSheetId, setRebalanceSheetId] = useState<string | null>(null);
  const rebalanceAlert = AI_ALERTS.find((a) => a.id === rebalanceSheetId) ?? null;
  const rebalanceHolding = rebalanceAlert ? ALL_HOLDINGS.find((h) => h.name === rebalanceAlert.stockName) : undefined;
  const rebalanceTargetPct = rebalanceHolding ? rebalanceHolding.target ?? rebalanceHolding.pct : 0;
  const rebalanceAdjustAmount = rebalanceHolding
    ? Math.round((HOLD_TOTAL * (rebalanceHolding.pct - rebalanceTargetPct)) / 100)
    : 0;

  // 보유 종목 테이블 — 정렬 열이 선택되면 그 기준으로, 아니면 원래 비중 순서 그대로 보여준다
  const sortedGains = useMemo(() => {
    if (!sortKey) return gains;
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...gains].sort((a, b) =>
      sortKey === 'name' ? a.name.localeCompare(b.name) * dir : (a[sortKey] - b[sortKey]) * dir
    );
  }, [gains, sortKey, sortDir]);

  // 보유 종목 테이블 "더보기" — 기본값은 접힌 상태(상위 10개만 노출)이고, 정렬 기준이 바뀌어도 펼침 여부는 유지한다.
  const [isHoldingsExpanded, setIsHoldingsExpanded] = useState(false);
  const HOLDINGS_PAGE_SIZE = 10;
  const visibleGains = isHoldingsExpanded ? sortedGains : sortedGains.slice(0, HOLDINGS_PAGE_SIZE);

  // 최근 거래 — 실 체결 내역(executions)이 있으면 그걸, 없으면 목업을 쓴다
  const displayTransactions = useMemo(() => getDisplayTransactions(executions), [executions]);

  if (view === 'review') {
    return (
      <ReviewView
        userName={userName}
        onNavigate={onNavigate}
        onBack={() => setView('main')}
      />
    );
  }

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          {/* PowerBI Embedded 페이지(`/portfolio`)로 돌아가는 상단 네비게이션 */}
          <button onClick={onBack} className="self-start text-[15px] text-muted">← 돌아가기</button>

          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">나의 포트폴리오</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
              {userName}님의 투자는<br />오늘도 전략대로 움직이고 있어요.
            </h1>
            <div className="flex items-baseline gap-4">
              <span className="text-[40px] font-bold tracking-[-0.035em]">{won(HOLD_TOTAL)}</span>
              <span className="text-xl font-bold text-up">
                오늘 {todayTotal >= 0 ? '+' : ''}{Math.round(todayTotal).toLocaleString('ko-KR')}원
              </span>
            </div>
          </section>

          {/* Dashboard.tsx 병합 — "오늘 무슨 일이 있었나요" 스토리 카드. 아래에 이미 있는
              리밸런싱 경고/현재 전략 카드와 겹치는 항목은 중복 제거하고, 여기 없던 두 카드만 가져왔다. */}
          <section className="flex flex-col gap-6">
            <h2 className="text-[32px] font-bold leading-[46px] tracking-[-0.03em]">오늘 내 투자에는 무슨 일이 있었나요?</h2>
            <div className="flex flex-col gap-4">
              <Story title={`${top.name}가 오늘 수익을 가장 많이 만들었어요`}>
                <div className="flex items-baseline gap-4">
                  <span className="text-2xl font-bold text-up">+{Math.round(top.gain).toLocaleString('ko-KR')}원</span>
                  <span className="text-[17px] text-muted">
                    오늘 전체 수익의 {todayTotal !== 0 ? Math.round((top.gain / todayTotal) * 100) : 0}%
                  </span>
                </div>
              </Story>
              <Story title="KT&G는 포트폴리오의 흔들림을 줄여줬어요">
                <span className="text-[17px] leading-7 text-muted">오늘 시장보다 변동성이 낮았어요.</span>
              </Story>
            </div>
          </section>

          {/* 현재 전략 + 변경 트리거 — Primary 로 강조하지 않는다 */}
          <section className="flex items-center justify-between gap-8 rounded-card bg-surface px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-[15px] text-muted">현재 전략</span>
              <span className="text-2xl font-bold tracking-[-0.025em]">{selectedStrategy.name}</span>
              <span className="text-base text-muted">나와 {selectedStrategy.match}% 잘 맞아요</span>
            </div>
            <button
              onClick={() => setModalOpen(true)}
              className="shrink-0 rounded-field bg-[#F4F6F1] px-7 py-4 text-[17px] font-semibold text-[#3F4A43]"
            >
              전략 변경하기
            </button>
          </section>

          {/* AI 손절/리밸런싱 제안 — 백엔드에 판단 로직이 아직 없어 목업이다. 배지를 누르거나
              "왜 지금인가요?"를 누르면 사유 모달이 열린다 */}
          {AI_ALERTS.length > 0 && (
            <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
              <div className="flex flex-col gap-2.5">
                <span className="text-base font-semibold text-[#3F5222]">✦ AI 제안</span>
                <h2 className="text-[26px] font-bold tracking-[-0.025em]">지금 확인해야 할 손절·리밸런싱 제안이 있어요</h2>
              </div>
              <div className="flex flex-col gap-4">
                {AI_ALERTS.map((a) => (
                  <div key={a.id} className="flex items-center justify-between gap-6 rounded-[20px] bg-canvas px-9 py-7">
                    <div className="flex flex-col gap-2">
                      <div className="flex items-center gap-2.5">
                        <span className={`rounded-full px-3 py-1.5 text-sm font-bold ${ALERT_BADGE[a.kind]}`}>{a.badge}</span>
                        <span className="text-[19px] font-bold tracking-[-0.02em]">{a.stockName}</span>
                      </div>
                      <p className="text-[16px] text-muted">{a.headline}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2.5">
                      <button
                        onClick={() => setAlertModalId(a.id)}
                        className="rounded-field bg-[#F4F6F1] px-6 py-3.5 text-[15px] font-semibold text-[#3F4A43]"
                      >
                        왜 지금인가요?
                      </button>
                      {a.kind === '리밸런싱' && (
                        <button
                          onClick={() => setRebalanceSheetId(a.id)}
                          className="rounded-field bg-lime px-6 py-3.5 text-[15px] font-bold text-navy"
                        >
                          조정 제안 확인하기
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* 보유 종목 테이블 — 헤더를 누르면 오름/내림차순 토글. AI 제안이 걸린 종목엔 이름 옆에 배지가 붙는다.
              투자 원금/수익률은 실 계좌 포지션(purchase_amount/return_rate)이 있으면 그 값을, 없으면 목업 값을 쓴다. */}
          <section className="flex flex-col gap-5 rounded-card bg-surface p-12">
            <div className="flex items-baseline justify-between">
              <h2 className="text-[26px] font-bold tracking-[-0.025em]">전체 {ALL_HOLDINGS.length}개 종목</h2>
              <span className="text-[15px] text-subtle">종목을 누르면 상세 정보를 볼 수 있어요</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse">
                <thead>
                  <tr className="border-b border-line">
                    {HOLDINGS_COLUMNS.map((c) => (
                      <th key={c.key} className={`pb-3 ${c.align === 'right' ? 'text-right' : 'text-left'}`}>
                        <button
                          onClick={() => toggleSort(c.key)}
                          className={`inline-flex items-center gap-1 text-[14px] font-semibold text-muted ${
                            c.align === 'right' ? 'flex-row-reverse' : ''
                          }`}
                        >
                          {c.label}
                          {sortKey === c.key
                            ? (sortDir === 'asc' ? <ChevronUp size={13} /> : <ChevronDown size={13} />)
                            : <ChevronsUpDown size={13} className="text-subtle" />}
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleGains.map((h) => {
                    const detailIndex = MOCK_HOLDINGS.findIndex((holding) => holding.name === h.name);
                    const alert = AI_ALERTS.find((a) => a.stockName === h.name);
                    return (
                      <tr
                        key={h.name}
                        onClick={() => detailIndex >= 0 && onSelectStock(detailIndex)}
                        className="cursor-pointer border-b border-line last:border-0 hover:bg-canvas"
                      >
                        <td className="py-4">
                          <div className="flex flex-col gap-1">
                            <div className="flex items-center gap-2.5">
                              <span className="text-[18px] font-semibold tracking-[-0.02em]">{h.name}</span>
                              {alert && (
                                <button
                                  onClick={(e) => { e.stopPropagation(); setAlertModalId(alert.id); }}
                                  className={`rounded-full px-2.5 py-1 text-xs font-bold ${ALERT_BADGE[alert.kind]}`}
                                >
                                  {alert.badge}
                                </button>
                              )}
                            </div>
                            <span className="text-[14px] text-subtle">{h.sector}</span>
                          </div>
                        </td>
                        <td className="py-4 text-right text-[17px] font-bold">{h.pct.toFixed(1)}%</td>
                        <td className="py-4 text-right text-[16px] text-muted">{won(h.principal)}</td>
                        <td className={`py-4 text-right text-[16px] font-semibold ${
                          h.returnRate > 0 ? 'text-up' : h.returnRate < 0 ? 'text-down' : 'text-subtle'
                        }`}>
                          {h.returnRate > 0 ? '+' : ''}{h.returnRate.toFixed(1)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {sortedGains.length > HOLDINGS_PAGE_SIZE && (
              <button
                onClick={() => setIsHoldingsExpanded((v) => !v)}
                className="self-center rounded-field bg-[#F4F6F1] px-8 py-3.5 text-[15px] font-semibold text-[#3F4A43]"
              >
                {isHoldingsExpanded ? '접기' : `더보기 (${sortedGains.length - HOLDINGS_PAGE_SIZE}개 더보기)`}
              </button>
            )}
          </section>

          {/* 최근 거래 — 실 체결 내역이 있으면 최신 3건, 없으면 목업 3건. 전체 내역은 별도 페이지로 라우팅한다 */}
          <section className="flex flex-col gap-5 rounded-card bg-surface p-12">
            <div className="flex items-baseline justify-between">
              <h2 className="text-[26px] font-bold tracking-[-0.025em]">최근 거래 내역</h2>
              <button onClick={() => onNavigate('transactions')} className="text-base font-semibold text-navy">더보기 →</button>
            </div>
            <div className="flex flex-col">
              {displayTransactions.slice(0, 3).map((t) => (
                <button
                  key={t.id}
                  onClick={() => onSelectTransaction(t.id)}
                  className="flex items-center gap-6 border-b border-line py-5 text-left last:border-0 hover:bg-canvas"
                >
                  <span className="w-24 shrink-0 text-[14px] text-subtle">{t.date}</span>
                  <span className={`w-[76px] shrink-0 rounded-full px-3 py-1.5 text-center text-sm font-bold ${TX_BADGE[t.type]}`}>
                    {t.type}
                  </span>
                  <span className="flex-1 text-[17px] font-semibold text-[#3F4A43]">{t.stockName}</span>
                  <span className={`shrink-0 text-[16px] font-bold ${t.amount >= 0 ? 'text-up' : 'text-down'}`}>
                    {t.amount >= 0 ? '+' : ''}{t.amount.toLocaleString('ko-KR')}원
                  </span>
                </button>
              ))}
            </div>
          </section>

          {/* AI 알고리즘 vs 내 포트폴리오 — 백엔드에 자동매매 비교 지표가 없어 목업이다.
              자동매매 전환을 유도하는 수익률 비교 카드 */}
          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <div className="flex flex-col gap-2.5">
              <h2 className="text-[26px] font-bold tracking-[-0.025em]">AI 알고리즘 vs 내 포트폴리오 수익률 한눈에 비교하기</h2>
              <p className="text-lg text-muted">{AUTO_VS_MANUAL.periodLabel} 동안 AI 제안을 그대로 따랐다면과 실제 내 선택을 비교해봤어요.</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2 rounded-[18px] bg-canvas px-8 py-7">
                <span className="text-[15px] text-muted">AI 알고리즘 (완전 자동)</span>
                <span className="text-[30px] font-bold tracking-[-0.03em] text-up">+{AUTO_VS_MANUAL.aiReturn.toFixed(1)}%</span>
                <span className="text-[14px] text-subtle">변동성 {AUTO_VS_MANUAL.aiVol.toFixed(1)}%</span>
              </div>
              <div className="flex flex-col gap-2 rounded-[18px] bg-canvas px-8 py-7">
                <span className="text-[15px] text-muted">내 포트폴리오 (실제)</span>
                <span className={`text-[30px] font-bold tracking-[-0.03em] ${AUTO_VS_MANUAL.myReturn >= 0 ? 'text-up' : 'text-down'}`}>
                  {AUTO_VS_MANUAL.myReturn >= 0 ? '+' : ''}{AUTO_VS_MANUAL.myReturn.toFixed(2)}%
                </span>
                <span className="text-[14px] text-subtle">변동성 {AUTO_VS_MANUAL.myVol.toFixed(1)}%</span>
              </div>
            </div>
            <Insight>
              {AUTO_VS_MANUAL.aiReturn > AUTO_VS_MANUAL.myReturn
                ? `이 기간에는 AI 제안을 모두 따랐다면 수익률이 ${(AUTO_VS_MANUAL.aiReturn - AUTO_VS_MANUAL.myReturn).toFixed(1)}%p 더 높았어요.`
                : '이 기간에는 내 선택이 AI 제안보다 더 좋은 결과를 냈어요.'}
            </Insight>
          </section>

          {/* "내 투자 판단은 어땠을까요?" — 요약 카드. 상세 회고는 "지난 판단 돌아보기"에서 서브뷰로 전환한다.
              백엔드에 판단 기록 API 가 없어 목업이다. */}
          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <div className="flex flex-col gap-3.5">
              <h2 className="text-[26px] font-bold tracking-[-0.025em]">내 투자 판단은 어땠을까요?</h2>
              <p className="text-lg leading-[30px] text-muted">
                AI 제안을 따랐을 때와 내가 선택한 결과를 함께 돌아볼 수 있어요.
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <span className="text-[15px] text-muted">지난 리밸런싱 제안</span>
              <div className="flex items-center gap-3.5 text-[19px] text-[#3F4A43]">
                <span>AI 제안 <b>{PAST_DECISIONS[0].action}</b></span>
                <span className="text-[#A6AFA7]">·</span>
                <span>내 선택 <b>{PAST_DECISIONS[0].choice === '수락' ? '수락함' : '하지 않음 (보류)'}</b></span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2 rounded-[18px] bg-canvas px-8 py-7">
                <span className="text-[15px] text-muted">AI 제안을 따랐다면</span>
                <span className="text-[26px] font-bold tracking-[-0.03em] text-up">{PAST_DECISIONS[0].result}</span>
              </div>
              <div className="flex flex-col gap-2 rounded-[18px] bg-canvas px-8 py-7">
                <span className="text-[15px] text-muted">실제 내 선택</span>
                <span className="text-[26px] font-bold tracking-[-0.03em] text-down">현재 자산 -3,800원</span>
              </div>
            </div>
            <p className="text-[17px] leading-7 text-muted">
              이번에는 AI 제안을 따랐을 때 변동성이 조금 더 낮았어요.
            </p>
            <button
              onClick={() => setView('review')}
              className="self-start text-base font-semibold text-navy"
            >
              지난 판단 돌아보기 →
            </button>
          </section>
        </div>
      </main>

      {/* 전략 변경 모달 — 현재 전략만 라임 테두리로 강조 */}
      {isModalOpen && (
        <div className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8" onClick={() => setModalOpen(false)}>
          <div className="flex w-[640px] flex-col gap-7 rounded-card bg-surface p-12" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-6">
              <div className="flex flex-col gap-2.5">
                <h2 className="text-[28px] font-bold tracking-[-0.03em]">어떤 전략으로 운용할까요?</h2>
                <p className="text-[17px] leading-7 text-muted">전략은 언제든 바꿀 수 있어요.</p>
              </div>
              <button aria-label="닫기" onClick={() => setModalOpen(false)} className="rounded-[9px] bg-canvas p-2 text-muted">
                <X size={18} />
              </button>
            </div>

            <div className="flex flex-col gap-3">
              {STRATEGIES.map((s) => {
                const active = s.id === selectedStrategy.id;
                return (
                  <button
                    key={s.id}
                    onClick={() => void setSelectedStrategy(s.id)}
                    className={`flex items-center justify-between rounded-[20px] px-8 py-7 text-left ${
                      active ? 'bg-[#F8FCEE] shadow-[0_0_0_2px_#C6F04D_inset]' : 'bg-canvas shadow-[0_0_0_1px_#E5E9E3_inset]'
                    }`}
                  >
                    <span className="text-[22px] font-bold tracking-[-0.02em]">{s.name}</span>
                    {active && (
                      <span className="rounded-full bg-lime px-3.5 py-2 text-sm font-bold text-navy">현재 전략</span>
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
        <div className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8" onClick={() => setAlertModalId(null)}>
          <div className="flex w-[560px] flex-col gap-6 rounded-card bg-surface p-11" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-6">
              <div className="flex flex-col gap-2.5">
                <span className={`w-fit rounded-full px-3 py-1.5 text-sm font-bold ${ALERT_BADGE[alertModal.kind]}`}>
                  {alertModal.badge}
                </span>
                <h2 className="text-[24px] font-bold tracking-[-0.025em]">{alertModal.stockName} · 왜 지금인가요?</h2>
              </div>
              <button aria-label="닫기" onClick={() => setAlertModalId(null)} className="rounded-[9px] bg-canvas p-2 text-muted">
                <X size={18} />
              </button>
            </div>
            <p className="text-[17px] leading-7 text-[#3F4A43]">{alertModal.reason}</p>
            <div className="flex items-center gap-3 rounded-[16px] bg-[#F8FCEE] px-7 py-6">
              <span className="shrink-0 text-[15px] font-semibold text-[#3F5222]">AI 제안</span>
              <span className="text-[16px] font-semibold text-ink">{alertModal.action}</span>
            </div>
          </div>
        </div>
      )}

      {/* Dashboard.tsx 병합 — 리밸런싱 "조정 전/후" 상세 시트. "조정 제안 확인하기" 클릭 시 연다. */}
      {rebalanceAlert && rebalanceHolding && (
        <div className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8" onClick={() => setRebalanceSheetId(null)}>
          <div className="flex w-[720px] flex-col gap-7 rounded-card bg-surface p-12" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-6">
              <h2 className="text-[28px] font-bold leading-10 tracking-[-0.03em]">왜 지금 비중을 조정하라고 하나요?</h2>
              <button aria-label="닫기" onClick={() => setRebalanceSheetId(null)} className="rounded-[9px] bg-canvas p-2 text-muted">
                <X size={18} />
              </button>
            </div>
            <p className="text-lg leading-[30px] text-[#3F4A43]">{rebalanceAlert.reason}</p>
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
            <div className="flex flex-col gap-2.5 rounded-[18px] bg-[#F8FCEE] px-8 py-7">
              <span className="text-lg font-bold tracking-[-0.02em]">조정하지 않으면?</span>
              <p className="text-[17px] leading-7 text-[#3F4A43]">
                특정 종목의 영향이 커져 {selectedStrategy.name}보다 포트폴리오가 더 많이 흔들릴 수 있어요.
              </p>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setRebalanceSheetId(null)} className="flex-1 rounded-field bg-lime py-5 text-lg font-bold text-navy">
                {won(Math.abs(rebalanceAdjustAmount))} 조정하기
              </button>
              <button onClick={() => setRebalanceSheetId(null)} className="rounded-field bg-[#F4F6F1] px-8 py-5 text-[17px] font-semibold text-[#3F4A43]">
                이번에는 하지 않을게요
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** PDF Page 5 — "내 투자 판단 돌아보기" 서브뷰. 라우터가 생기면 `/portfolio/review` 로 그대로 옮길 수 있다 */
function ReviewView({ userName, onNavigate, onBack }: { userName: string; onNavigate: (s: Screen) => void; onBack: () => void }) {
  const maxVol = Math.max(DECISION_SUMMARY.volIfFollowed, DECISION_SUMMARY.volActual);

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <button onClick={onBack} className="self-start text-[15px] text-muted">← 포트폴리오 대시보드로 돌아가기</button>

          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">투자 판단 기록</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">내 투자 판단 돌아보기</h1>
            <p className="text-[19px] leading-8 text-muted">
              AI 제안과 내가 내린 선택이 이후 포트폴리오에 어떤 차이를 만들었는지 살펴볼 수 있어요.
            </p>
          </section>

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex items-center justify-between">
              <h2 className="text-[22px] font-bold tracking-[-0.025em]">요약 통계</h2>
              <span className="rounded-full bg-[#F4F6F1] px-4 py-2 text-sm font-semibold text-[#3F4A43]">{DECISION_SUMMARY.periodLabel}</span>
            </div>
            <div className="grid grid-cols-3 gap-8">
              <Stat label="AI 제안" value={`${DECISION_SUMMARY.proposed}회`} />
              <Stat label="수락" value={`${DECISION_SUMMARY.accepted}회`} />
              <Stat label="보류" value={`${DECISION_SUMMARY.held}회`} />
            </div>
          </section>

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <h2 className="text-[22px] font-bold tracking-[-0.025em]">AI 제안을 따랐을 때 vs 내 실제 선택</h2>
            <div className="grid grid-cols-2 gap-10">
              <VolBar label="AI 제안을 따랐을 때" value={DECISION_SUMMARY.volIfFollowed} max={maxVol} good />
              <VolBar label="내 실제 선택" value={DECISION_SUMMARY.volActual} max={maxVol} />
            </div>
            <Insight>이번 기간에는 AI 제안을 따랐을 때 포트폴리오의 변동성이 조금 더 낮았어요.</Insight>
          </section>

          <section className="flex flex-col gap-5 rounded-card bg-surface p-12">
            <div className="flex items-baseline justify-between">
              <h2 className="text-[22px] font-bold tracking-[-0.025em]">최근 판단 기록</h2>
              <span className="text-[15px] text-subtle">최근 {PAST_DECISIONS.length}건</span>
            </div>
            <div className="flex flex-col">
              {PAST_DECISIONS.map((d) => (
                <div key={d.date} className="flex items-center gap-6 border-b border-line py-5 last:border-0">
                  <span className="w-24 shrink-0 text-[14px] text-subtle">{d.date}</span>
                  <span className="flex-1 text-[17px] font-semibold text-[#3F4A43]">{d.action}</span>
                  <span
                    className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-bold ${
                      d.choice === '수락' ? 'bg-[#EAF7EF] text-[#2E9B65]' : 'bg-[#F4F6F1] text-muted'
                    }`}
                  >
                    ● {d.choice}
                  </span>
                  <span className="w-48 shrink-0 text-right text-[15px] text-muted">{d.result}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

/** Dashboard.tsx 병합 — "오늘 무슨 일이 있었나요" 스토리 카드 껍데기 */
function Story({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3.5 rounded-card bg-surface px-11 py-10">
      <span className="text-[26px] font-bold leading-[38px] tracking-[-0.025em]">{title}</span>
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

function VolBar({ label, value, max, good }: { label: string; value: number; max: number; good?: boolean }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <span className="text-[17px] font-semibold text-[#3F4A43]">{label}</span>
        <span className="text-[22px] font-bold tracking-[-0.02em]">{value.toFixed(1)}%</span>
      </div>
      <div className="h-2.5 rounded-full bg-[#E5E9E3]">
        <div
          className={`h-2.5 rounded-full ${good ? 'bg-lime' : 'bg-[#C3CBC4]'}`}
          style={{ width: `${(value / max) * 100}%` }}
        />
      </div>
      <span className="text-[15px] text-muted">
        변동성 지표가 상대적으로 {good ? '낮은' : '높은'} 편이에요.
      </span>
    </div>
  );
}

function Insight({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-4 rounded-[18px] bg-[#F8FCEE] px-8 py-6">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-lime text-base text-navy">✦</div>
      <p className="pt-0.5 text-[17px] leading-7 text-[#3F4A43]">{children}</p>
    </div>
  );
}
