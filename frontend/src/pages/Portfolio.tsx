import { useEffect, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Sector, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Maximize2, X } from 'lucide-react';
import Header from '../components/Header';
import {
  ALL_HOLDINGS as MOCK_HOLDINGS, HOLD_TOTAL as MOCK_HOLD_TOTAL,
  PORTFOLIO_TREND, STOCK_CONTRIBUTION, STOCK_INFO,
} from '../data/holdings';
import { useTradingData } from '../hooks/useTradingData';
import { getPortfolioHistoryApi, type PortfolioHistoryPeriod, type PortfolioHistoryResponse } from '../lib/backendApi';
import { getDisplayAlerts } from '../lib/rebalancing';
import { getDisplayTransactions } from '../lib/transactions';
import { won } from '../lib/validation';
import { useAuthStore } from '../store/authStore';
import { useTradingStore } from '../store/tradingStore';
import type { Screen, TransactionRecord } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  /** "자세히" — 보유종목/AI 제안/거래내역 등 전체 관리 화면(PortfolioDetail)으로 이동한다 */
  onOpenDetail: () => void;
  /** 미설정 유저 안내 모달의 "투자성향 진단하러 가기" — 투자자 정보 확인(risk) Flow로 보낸다.
   *  'strategy'/'start'(전략 둘러보기/계좌 연동·입금)는 이미 있는 onNavigate 로 충분해 별도 prop 을 두지 않았다. */
  onStartRiskProfile: () => void;
}

/** 미설정 유저 안내 모달 — 어떤 항목이 비어있는지에 따라 문구/버튼이 달라진다.
 *  세 항목을 동시에 검사해서 "먼저 걸리는 것" 하나만 보여준다(투자성향 → 계좌/입금 → 전략 순). */
type UnconfiguredReason = 'risk' | 'account' | 'strategy';
const UNCONFIGURED_COPY: Record<UnconfiguredReason, { title: string; message: string; cta: string }> = {
  risk: {
    title: '아직 투자성향을 진단하지 않으셨어요!',
    message: '고객님의 안전하고 정확한 포트폴리오 구성을 위해 투자 성향 진단이 필요합니다.',
    cta: '투자성향 진단하러 가기',
  },
  account: {
    title: '아직 계좌 연동·입금을 완료하지 않으셨어요!',
    message: '자산 분석 및 AI 투자를 진행하기 위해 계좌 연동 및 입금을 진행해주세요.',
    cta: '계좌 연동 / 입금하기',
  },
  strategy: {
    title: '아직 투자 전략을 선택하지 않으셨어요!',
    message: '맞춤형 AI 포트폴리오를 구성하기 위해 원하시는 투자 전략을 선택해주세요.',
    cta: '전략 둘러보기',
  },
};

/** Power BI 임베드 그래프 변형 3종 — 탭 전환 대상 (위험 분석 탭은 미사용으로 제거됨) */
type AnalyticsTab = 'weight' | 'trend' | 'contribution';
const ANALYTICS_TABS: { id: AnalyticsTab; label: string }[] = [
  { id: 'weight', label: '요약' },
  { id: 'trend', label: '자산 변화' },
  { id: 'contribution', label: '종목별 기여' },
];

// 실 계좌가 있으면 GET /portfolio/history 가 기간별로 직접 필터링해서 내려준다(서버 사이드 기간 필터).
// 실 계좌가 없을 때만 목업 PORTFOLIO_TREND 를 포인트 개수로 잘라 쓴다 — n:1 이면 라인 차트에 점이
// 하나뿐이라(dot={false}) 아무것도 안 보이니 최소 2개 포인트를 보장한다.
const TREND_PERIODS: { label: string; value: PortfolioHistoryPeriod; mockN: number }[] = [
  { label: '1개월', value: '1M', mockN: 2 },
  { label: '3개월', value: '3M', mockN: 3 },
  { label: '1년', value: '1Y', mockN: PORTFOLIO_TREND.length },
  { label: '전체', value: 'ALL', mockN: PORTFOLIO_TREND.length },
];

/** 도넛(보유 비중) 색 — 선택된 조각만 라임, 나머지는 순환 셰이드 */
const DONUT_SHADES = ['#18243A', '#2E4160', '#4A5F80', '#6C819E', '#8FA0B4', '#C3CBC4'];

/** 클릭해서 선택한 조각만 크기가 커지는 애니메이션 — recharts 의 activeShape/activeIndex 조합으로,
 *  선택된 조각의 outerRadius 만 살짝 키운 Sector 를 대신 그린다(색은 원래 Cell 의 fill 을 그대로 쓴다).
 *  Pie 는 기본적으로 애니메이션이 켜져 있어(isAnimationActive), 반경 변화가 자연스럽게 트랜지션된다. */
function ActiveDonutSector(props: {
  cx?: number;
  cy?: number;
  innerRadius?: number;
  outerRadius?: number;
  startAngle?: number;
  endAngle?: number;
  fill?: string;
}) {
  const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill } = props;
  return (
    <Sector
      cx={cx}
      cy={cy}
      innerRadius={innerRadius}
      outerRadius={(outerRadius ?? 0) + 10}
      startAngle={startAngle}
      endAngle={endAngle}
      fill={fill}
    />
  );
}

/** AI 손절/리밸런싱 제안 배지 색 — 우측 하단 위젯과 사유 팝업이 공유한다 */
const ALERT_BADGE: Record<'손절' | '리밸런싱', string> = {
  '손절': 'bg-[#FBEAEA] text-up',
  '리밸런싱': 'bg-[#FCF3E4] text-warn',
};

/** 최근 거래 유형 배지 색 */
const TX_BADGE: Record<TransactionRecord['type'], string> = {
  '매수': 'bg-[#F4F6F1] text-[#3F4A43]',
  '매도': 'bg-[#EAF2FD] text-down',
  '리밸런싱': 'bg-[#FCF3E4] text-warn',
  '배당': 'bg-[#F8FCEE] text-[#3F5222]',
};

/** 실 계좌가 없을 때 "내 투자 총금액"에 쓰는 목업 투자 원금 합계 */
const MOCK_PRINCIPAL_TOTAL = MOCK_HOLDINGS.reduce((sum, h) => sum + (h.principal ?? 0), 0);

/** `/portfolio` — 스크롤 없이 한 화면에 담기는 요약 뷰. 보유종목·AI제안·거래내역·전략변경 등
 *  나머지 포트폴리오 관리 기능은 전부 "자세히" → PortfolioDetail.tsx(`/portfolio/detail`)로 분리했다.
 *  보유 비중 탭은 실 계좌(useTradingStore.portfolio)가 있으면 그 데이터를, 없으면
 *  MOCK_HOLDINGS 로 대체해 보여준다 — 이 대체 규칙은 PortfolioDetail.tsx 와 동일하게 맞춰뒀다. */
export default function Portfolio({ userName, onNavigate, onOpenDetail, onStartRiskProfile }: Props) {
  useTradingData();
  const portfolio = useTradingStore((state) => state.portfolio);
  const executions = useTradingStore((state) => state.executions);
  const accessToken = useAuthStore((state) => state.accessToken);
  // 미설정 유저 감지 — investorProfileCompleted(투자성향)는 로그인/새로고침마다 백엔드
  // (/investor-profile/me/latest)에서 다시 복원하는 값이라, 조회가 끝나기 전(isInvestorProfileHydrating)에는
  // 아직 false 인 게 "진짜 미진단"인지 "복원 중이라 아직 모르는 것"인지 구분할 수 없다. 그래서
  // "계좌에 전략이 이미 선택돼 있다(account.selected_strategy_id)"를 가장 먼저 확인한다 — 실제 투자 시작
  // Flow는 반드시 투자성향 진단 → 계좌/입금 → 전략 선택 순서를 강제하므로, 전략이 선택돼 있다는 것 자체가
  // 앞 단계를 모두 마쳤다는 더 확실한 증거다. 이 신호가 없을 때만 세션 상태로 투자성향 → 계좌/입금 → 전략
  // 순서를 확인한다. 계좌 데이터를 아직 못 불러온 로딩 중(isAccountLoading)에는 account/accountMissing 이
  // 둘 다 초기값(null/false)이라 오판할 수 있어, 두 로딩이 모두 끝난 뒤에만 판정한다.
  const investorProfileCompleted = useAuthStore((state) => state.investorProfileCompleted);
  const isInvestorProfileHydrating = useAuthStore((state) => state.isInvestorProfileHydrating);
  const account = useTradingStore((state) => state.account);
  const accountMissing = useTradingStore((state) => state.accountMissing);
  const isAccountLoading = useTradingStore((state) => state.isLoading);
  const unconfiguredReason: UnconfiguredReason | null = isAccountLoading || isInvestorProfileHydrating
    ? null
    : account?.selected_strategy_id
      ? null
      : !investorProfileCompleted
        ? 'risk'
        : accountMissing
          ? 'account'
          : 'strategy';

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
      };
    });
  }, [portfolio]);

  // 자산 증감 요약 — 실 계좌가 있으면 백엔드가 이미 계산해 둔 계좌 손익(unrealized_profit + realized_profit, return_rate)을
  // 그대로 쓴다. total_assets - total_purchase_amount 로 직접 빼면 total_assets 에 포함된 미투자 현금(cash_balance)이
  // 수익으로 잡히는 문제가 있어(예: 매수 전 예치금만 있어도 +100% 로 표시됨) 이 방식은 쓰지 않는다.
  const principalTotal = portfolio ? Number(portfolio.total_purchase_amount) : MOCK_PRINCIPAL_TOTAL;
  const holdTotal = portfolio ? Number(portfolio.total_assets) : MOCK_HOLD_TOTAL;
  const mockGainAmount = holdTotal - principalTotal;
  const gainAmount = portfolio ? Number(portfolio.unrealized_profit) + Number(portfolio.realized_profit) : mockGainAmount;
  const gainPct = portfolio ? Number(portfolio.return_rate) : (principalTotal > 0 ? (mockGainAmount / principalTotal) * 100 : 0);

  // ── Power BI 스타일 분석 섹션 상태 ───────────────────────────────
  const [tab, setTab] = useState<AnalyticsTab>('weight');
  const [historyPeriod, setHistoryPeriod] = useState<PortfolioHistoryPeriod>('1Y'); // 기본값 "1년"
  const [history, setHistory] = useState<PortfolioHistoryResponse | null>(null);
  const [selectedHoldingIdx, setSelectedHoldingIdx] = useState(0);
  // 도넛을 실제로 클릭한 적이 있는지 — 클릭 전에는 중앙 라벨이 기본값("총 자산 100%")을 유지하다가,
  // 한 번 클릭하면 그 조각으로 고정된다(hasSelectedHolding 이 true 로 바뀐 뒤에는 selectedHoldingIdx 를 계속 보여준다).
  const [hasSelectedHolding, setHasSelectedHolding] = useState(false);
  // 도넛 위에 마우스를 올린 조각 — 호버 중에는 고정된 선택보다 우선해서 도넛 중앙 라벨을 잠깐 바꿔 보여준다
  const [hoverHoldingIdx, setHoverHoldingIdx] = useState<number | null>(null);
  // 실 계좌에 리밸런싱 제안이 있으면 그 값을, 없으면 목업을 쓴다 — lib/rebalancing.ts 참고
  const displayAlerts = useMemo(() => getDisplayAlerts(portfolio), [portfolio]);
  // 우측 하단 "AI 제안" 위젯에서 카드를 클릭하면 여는 사유 팝업 — id 로 열림 상태를 관리한다
  const [alertModalId, setAlertModalId] = useState<string | null>(null);
  const alertModal = displayAlerts.find((a) => a.id === alertModalId) ?? null;
  // 차트 우상단 "크게 보기" 픽토그램 — 세 탭(요약/자산 변화/종목별 기여) 모두에서 쓰며,
  // 클릭 시 현재 tab 이 가리키는 차트를 그대로 훨씬 큰 크기의 팝업으로 다시 그린다.
  const [isChartZoomOpen, setIsChartZoomOpen] = useState(false);

  // 우측 하단 "최근 거래" 위젯 — 실 체결 내역(executions)이 있으면 그걸, 없으면 목업으로 대체한다.
  // 가로 3칸 레이아웃이라 항상 최신 3건만 보여준다.
  const recentTransactions = useMemo(() => getDisplayTransactions(executions).slice(0, 3), [executions]);

  // 자산 변화 탭: 실 계좌가 있으면 GET /portfolio/history 를 선택된 기간으로 다시 조회한다(서버가 기간별로
  // 필터링해 내려주므로 클라이언트에서 자를 필요가 없다). 계좌가 없거나 그 계좌에 아직 쌓인 이력이 없으면
  // (신규 계좌) 목업 추이를 기존과 동일하게 포인트 개수로 잘라 보여준다.
  useEffect(() => {
    if (!account || !accessToken) { setHistory(null); return; }
    let cancelled = false;
    getPortfolioHistoryApi(account.id, historyPeriod, accessToken)
      .then((r) => { if (!cancelled) setHistory(r); })
      .catch(() => { if (!cancelled) setHistory(null); });
    return () => { cancelled = true; };
  }, [account, accessToken, historyPeriod]);

  const trendData = useMemo(() => {
    if (history && history.items.length > 0) {
      return history.items.map((item) => ({
        label: item.date.slice(5).replace('-', '.'),
        port: Number(item.portfolio_return_rate),
        kospi: item.benchmark_return_rate == null ? 0 : Number(item.benchmark_return_rate),
      }));
    }
    const mockN = TREND_PERIODS.find((p) => p.value === historyPeriod)?.mockN ?? PORTFOLIO_TREND.length;
    return PORTFOLIO_TREND.slice(-mockN);
  }, [history, historyPeriod]);
  const benchmarkName = history?.benchmark_name ?? 'KOSPI';

  // 종목별 기여 탭: 실 계좌가 있고 기여도가 산출됐으면 그 값을, 없으면 목업을 큰 기여 순으로 정렬해 보여준다.
  const contributionData = useMemo(() => {
    if (portfolio && portfolio.contributions.length > 0) {
      return [...portfolio.contributions]
        .map((c) => ({ name: c.stock_name ?? c.stock_code, amount: Number(c.amount) }))
        .sort((a, b) => b.amount - a.amount);
    }
    return [...STOCK_CONTRIBUTION].sort((a, b) => b.amount - a.amount);
  }, [portfolio]);
  const topContributor = contributionData[0];

  // 보유 비중 탭: 선택된 종목의 현재 비중 vs 전략 목표 비중
  const safeSelectedIndex = Math.min(selectedHoldingIdx, Math.max(ALL_HOLDINGS.length - 1, 0));
  const selectedHolding = ALL_HOLDINGS[safeSelectedIndex];
  const targetPct = selectedHolding.target ?? selectedHolding.pct;
  const weightDiff = Math.round((selectedHolding.pct - targetPct) * 10) / 10;

  // 도넛 차트 + 중앙 라벨 — 컬럼 안의 작은 버전과 "크게 보기" 팝업의 확대 버전이 이 렌더 함수를 그대로 공유한다.
  // sizeClass 만 다르게 넘겨서 같은 인터랙션(호버 라벨/클릭 선택/activeShape 확대)을 두 크기에서 동일하게 쓴다.
  // onExpand 를 넘긴 쪽(작은 버전)에만 "크게 보기" 버튼이 도넛 자체의 우상단에 붙는다.
  const renderDonutChart = (sizeClass: string, onExpand?: () => void) => (
    <div className={`relative donut-no-focus-outline ${sizeClass}`}>
      {onExpand && (
        <button
          aria-label="차트 크게 보기"
          onClick={onExpand}
          className="absolute right-0 top-0 z-10 rounded-[9px] bg-[#C6F04D] p-2 text-muted hover:text-ink"
        >
          <Maximize2 size={16} />
        </button>
      )}
      {/* recharts 조각(g[tabindex])이 클릭되면 브라우저가 기본 포커스 테두리를 그리는데,
          이 컴포넌트 안에서만 지우도록 클래스로 스코프를 좁혀 다른 화면 접근성에는 영향을 주지 않는다. */}
      <style>{`
        .donut-no-focus-outline .recharts-pie-sector:focus,
        .donut-no-focus-outline .recharts-sector:focus,
        .donut-no-focus-outline .recharts-surface:focus,
        .donut-no-focus-outline .recharts-surface *:focus {
          outline: none;
        }
      `}</style>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          {/* 확대된 도넛 — outerRadius 를 컨테이너 가장자리(100%)가 아니라 85%로 살짝 안쪽에 둬서
              activeShape 로 커지는 조각(outerRadius+10)이 카드 밖으로 잘리지 않게 여유를 준다.
              innerRadius 55%로 링을 조금 더 두껍게 키워 시각적 중심(centerpiece) 역할을 강조한다. */}
          <Pie
            data={ALL_HOLDINGS}
            dataKey="pct"
            nameKey="name"
            innerRadius="55%"
            outerRadius="85%"
            startAngle={90}
            endAngle={-270}
            paddingAngle={1}
            stroke="none"
            // 클릭하면 선택 + "고정" 상태를 함께 켠다 — 이후 마우스가 도넛을 벗어나도
            // 중앙 라벨이 총 자산으로 되돌아가지 않고 이 조각 값에 고정된 채 유지된다.
            onClick={(_, i) => { setSelectedHoldingIdx(i); setHasSelectedHolding(true); }}
            // 호버 이벤트 — recharts는 조각의 인덱스를 두 번째 인자로 넘겨준다.
            // 호버 중에는 고정된 값보다 우선해서 중앙 라벨을 바꿔 보여주고, 벗어나면 고정된 값(없으면 총 자산 100%)으로 되돌린다.
            onMouseEnter={(_, i) => setHoverHoldingIdx(i)}
            onMouseLeave={() => setHoverHoldingIdx(null)}
            // 클릭해서 선택한 조각만 커지는 애니메이션 — activeIndex 가 가리키는 조각을
            // ActiveDonutSector(outerRadius+10)로 다시 그려서 강조한다.
            activeIndex={selectedHoldingIdx}
            activeShape={ActiveDonutSector}
          >
            {ALL_HOLDINGS.map((h, i) => (
              <Cell
                key={h.name}
                fill={i === selectedHoldingIdx ? '#C6F04D' : DONUT_SHADES[i % DONUT_SHADES.length]}
                cursor="pointer"
              />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      {/* 도넛 중앙 라벨 — 커서를 따라다니는 기본 Tooltip 대신, 호버(또는 클릭으로 고정된) 조각의 "종목명 : n%"를
          도넛 링 한가운데에 직접 렌더링한다(activeShape 대신 상태 기반 커스텀 라벨).
          우선순위: 지금 호버 중인 조각 > 클릭으로 고정된 조각 > 기본값(총 자산 100%). */}
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1 px-6 text-center">
        {(() => {
          const centerIdx = hoverHoldingIdx ?? (hasSelectedHolding ? selectedHoldingIdx : null);
          if (centerIdx === null) {
            return (
              <>
                <span className="text-sm text-muted">총 자산</span>
                <span className="text-2xl font-bold tracking-[-0.03em]">100%</span>
              </>
            );
          }
          const centerHolding = ALL_HOLDINGS[centerIdx];
          // chg 는 실 계좌 등락률이 아직 없으면 null 일 수 있다 — 표시상 0(보합)으로 취급한다.
          const chg = centerHolding.chg ?? 0;
          return (
            <>
              <span className="text-sm font-semibold text-ink">{centerHolding.name}</span>
              {/* 비중(n%) 색상을 해당 종목의 수익률 부호로 표현한다 — 이 앱의 다른 화면과 동일하게
                  수익(상승)은 text-up, 손해(하락)는 text-down 을 쓴다. */}
              <span className={`text-2xl font-bold tracking-[-0.03em] ${chg >= 0 ? 'text-up' : 'text-down'}`}>
                {centerHolding.pct.toFixed(1)}%
              </span>
              {/* 수익률에는 +/- 부호를 그대로 노출한다(양수는 +, 음수는 - 가 toFixed 에 이미 포함됨) */}
              <span className={`text-xs font-bold ${chg >= 0 ? 'text-up' : 'text-down'}`}>
                {chg >= 0 ? '+' : ''}
                {chg.toFixed(1)}%
              </span>
            </>
          );
        })()}
      </div>
    </div>
  );

  // 자산 변화(Line) 차트 — 컬럼 안의 작은 버전과 팝업의 확대 버전이 공유한다.
  // "크게 보기" 버튼은 도넛과 달리 absolute 가 아니라, 기간 선택 버튼들과 같은 줄(우측)에 넣는다 —
  // 그 자리가 이미 비어 있는 헤더 줄이라 겹치지 않고, 별도 여백 계산도 필요 없다.
  const renderTrendChart = (heightClass: string, onExpand?: () => void) => (
    <div className={`flex flex-col gap-3 ${heightClass}`}>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2">
          {TREND_PERIODS.map((p) => (
            <button
              key={p.value}
              onClick={() => setHistoryPeriod(p.value)}
              className={`rounded-full px-4 py-2 text-sm font-semibold ${
                p.value === historyPeriod ? 'bg-lime text-navy' : 'bg-[#F4F6F1] text-muted'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-subtle">비교 기준 <b className="text-[#3F4A43]">{benchmarkName}</b></span>
          {onExpand && (
            <button
              aria-label="차트 크게 보기"
              onClick={onExpand}
              className="shrink-0 rounded-[9px] bg-[#C6F04D] p-2 text-muted hover:text-ink"
            >
              <Maximize2 size={16} />
            </button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={trendData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#F0F2ED" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: '#8A948C', fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis
              tick={{ fill: '#8A948C', fontSize: 13 }}
              axisLine={false}
              tickLine={false}
              width={52}
              tickFormatter={(v: number) => `${v}%`}
            />
            <Tooltip formatter={(v: number) => `${v}%`} />
            <Legend iconType="plainline" wrapperStyle={{ fontSize: 13, color: '#5C665F' }} />
            <Line type="monotone" dataKey="kospi" name={benchmarkName} stroke="#C3CBC4" strokeWidth={3.5} dot={false} />
            <Line type="monotone" dataKey="port" name="내 포트폴리오" stroke="#18243A" strokeWidth={5} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );

  // 종목별 기여(Bar) 차트 — 마찬가지로 작은 버전과 팝업이 공유한다.
  const renderContributionChart = (heightClass: string, onExpand?: () => void) => (
    <div className={`flex flex-col gap-3 ${heightClass}`}>
      <div className="flex shrink-0 items-center justify-between gap-3">
        <p className="text-sm text-subtle">최근 1개월 동안 각 종목이 전체 수익에 얼마나 영향을 줬는지 보여줘요.</p>
        {onExpand && (
          <button
            aria-label="차트 크게 보기"
            onClick={onExpand}
            className="shrink-0 rounded-[9px] bg-[#C6F04D] p-2 text-muted hover:text-ink"
          >
            <Maximize2 size={16} />
          </button>
        )}
      </div>
      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={contributionData} layout="vertical" margin={{ left: 24, right: 24 }}>
            <CartesianGrid stroke="#F0F2ED" horizontal={false} />
            <XAxis type="number" tickFormatter={(v: number) => won(v)} tick={{ fill: '#8A948C', fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" width={90} tick={{ fill: '#5C665F', fontSize: 13 }} axisLine={false} tickLine={false} />
            <Tooltip formatter={(v: number) => won(v)} />
            <Bar dataKey="amount" radius={8} barSize={16}>
              {contributionData.map((d) => (
                <Cell key={d.name} fill={d.amount >= 0 ? '#18243A' : '#C24A4A'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );

  return (
    // AI 제안 사유 팝업을 페이지 루트(h-screen overflow-hidden)의 형제로 두기 위해 Fragment 로 감싼다.
    <>
    {/* 뷰포트가 넉넉하면 한 화면(h-screen)에 다 담기도록 아래 flex 트리를 가용 높이에 맞춰 나누고,
        화면이 작아 다 안 들어가면 잘라내는 대신(overflow-hidden 대신 overflow-y-auto) 페이지 자체가 스크롤된다. */}
    <div className="flex h-screen flex-col overflow-y-auto bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      {/* 헤더를 뺀 나머지 영역 전부를 차지한다(min-h-0 이 없으면 flex 자식이 넘칠 때 부모를 밀어낸다). */}
      <main className="flex min-h-0 flex-1 flex-col items-center px-4 pb-6 pt-4 sm:px-8 lg:px-16">
        <div className="flex min-h-0 w-full max-w-[1040px] flex-1 flex-col">
          {/* "나의 포트폴리오" 카드 — 제목/탭은 카드 상단에 걸치고, 그 아래는 넓은 화면(lg 이상)에서
              좌(차트) : 우(투자 정보) = 1:1 그리드(grid-cols-2), 좁은 화면에서는 세로로 쌓는다(grid-cols-1). */}
          <section className="flex flex-col gap-3 rounded-card bg-surface p-8 lg:min-h-0 lg:flex-1">
            <div className="flex shrink-0 items-start justify-between gap-6">
              <div className="flex flex-col gap-1">
                <h1 className="text-2xl font-bold tracking-[-0.02em]">나의 포트폴리오</h1>
              </div>
            </div>

            {/* 그래프 변형 스위처 — 요약(Donut) / 자산변화(Line) / 종목별기여(Bar) */}
            <div className="flex shrink-0 flex-wrap gap-1 border-b border-line pb-1">
              {ANALYTICS_TABS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`rounded-t-[10px] px-4 py-2.5 text-sm font-semibold ${
                    tab === t.id ? 'bg-canvas text-ink' : 'text-muted'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* 좌(차트) : 우(투자 정보) 1:1 그리드 — lg 이상에서는 grid-cols-2 로 두 컬럼을 정확히 절반씩 나누고,
                그보다 좁으면 grid-cols-1 로 세로로 쌓는다(작은 화면에서 잘리는 대신 아래로 이어짐). */}
            <div className="grid grid-cols-1 gap-6 lg:min-h-0 lg:flex-1 lg:grid-cols-2">
              {/* 왼쪽 컬럼(50%, lg 미만에서는 100%) — 현재 탭의 차트. "자세히" 버튼은 이 컬럼의 하단 중앙에 고정한다
                  (relative + absolute, 카드 전체가 아니라 차트 컬럼 기준 좌표). min-h 는 grid-cols-1 로 쌓일 때
                  차트가 찌그러지지 않도록 하는 최소 높이이고, lg 이상에서는 grid 행 높이에 맞춰 min-h-0 로 되돌아간다. */}
              <div className="relative flex min-h-[420px] flex-col gap-3 lg:min-h-0 lg:pb-14">
                {tab === 'trend' && (
                  <div className="flex h-full flex-col gap-3">
                    {/* "크게 보기" 버튼은 기간 선택 버튼들과 같은 헤더 줄(우측)에 있다(renderTrendChart 내부, onExpand) */}
                    {renderTrendChart('h-full', () => setIsChartZoomOpen(true))}
                    <Insight compact>
                      {trendData[trendData.length - 1].port >= trendData[trendData.length - 1].kospi
                        ? '시장보다 덜 흔들리면서 더 높은 누적 수익을 내고 있어요.'
                        : '최근 구간에서는 KOSPI가 더 좋았지만, 변동성은 여전히 낮게 유지되고 있어요.'}
                    </Insight>
                  </div>
                )}

                {tab === 'contribution' && (
                  <div className="flex h-full flex-col gap-3">
                    {/* "크게 보기" 버튼은 캡션 문구와 같은 헤더 줄(우측)에 있다(renderContributionChart 내부, onExpand) */}
                    {renderContributionChart('h-full', () => setIsChartZoomOpen(true))}
                    <Insight compact>{topContributor.name}가 수익에 가장 많이 기여했어요.</Insight>
                  </div>
                )}

                {tab === 'weight' && (
                  <div className="flex h-full flex-col items-center justify-center gap-4">
                    {/* 포트폴리오 배분 도넛 차트 — 왼쪽 컬럼의 시각적 중심(centerpiece).
                        "크게 보기" 버튼은 이 컬럼이 아니라 도넛 자체의 우상단에 붙는다(renderDonutChart 내부, onExpand). */}
                    {renderDonutChart('h-full max-h-[420px] w-full max-w-[420px]', () => setIsChartZoomOpen(true))}
                    {/* 선택/호버 시 종목명·비중·수익률은 도넛 중앙 라벨(위)이 이미 보여주므로 여기서는 중복 표시하지 않는다.
                        비워진 자리는 아래 Insight 와, 컬럼 우하단에 고정된 "자세히" 버튼이 채운다. */}
                    <Insight compact>
                      {weightDiff > 0
                        ? `${selectedHolding.name} 비중이 목표보다 높아요.`
                        : weightDiff < 0
                          ? `${selectedHolding.name} 비중이 목표보다 낮아요.`
                          : `${selectedHolding.name} 비중이 목표와 일치해요.`}
                    </Insight>
                  </div>
                )}

                {/* "자세히" — 클릭 시 보유종목/AI제안/거래내역 등 전체 관리 화면(portfolio-detail)으로 라우팅한다.
                    lg 이상(좌우 1:1 그리드)에서는 왼쪽(차트) 컬럼의 하단 중앙에 절대 위치로 고정하고,
                    그 미만(세로로 쌓이는 화면)에서는 컬럼 안 일반 흐름으로 둬서 다른 콘텐츠와 겹치지 않게 한다. */}
                <button
                  onClick={onOpenDetail}
                  className="static mt-2 self-center rounded-field bg-lime px-6 py-3 text-sm font-bold text-navy shadow-[0_4px_16px_rgba(24,36,58,0.18)] lg:absolute lg:bottom-0 lg:left-1/2 lg:mt-0 lg:-translate-x-1/2"
                >
                  자세히 보기
                </button>
              </div>

              {/* 오른쪽 컬럼(50%, lg 미만에서는 100%) — 투자 정보 + 향후 위젯을 위한 예약 공간. 탭과 무관하게 항상 동일하게 보여준다. */}
              {/* self-center — grid 행의 기본 stretch 를 끄고 콘텐츠 높이만큼만 차지하게 하면서(빈 여백 없음),
                  왼쪽 도넛(justify-center 로 컬럼 안에서 수직 중앙 정렬됨)과 같은 수직 중심선에 맞춘다.
                  grid-cols-1 로 쌓이는 화면에서는 w-full 이 없으면 콘텐츠 너비만큼만 좁게 잡혀 보기 어색해진다. */}
              <div className="flex min-h-0 w-full flex-col gap-4 self-center rounded-[20px] bg-canvas px-8 py-6">
                {/* 상단 — 와이어프레임과 동일하게 "나의 투자" 라벨 + 총 자산 금액 + 증감액(%)을 한 줄에 배치한다.
                    내 투자 총금액(원금)은 이 줄에서는 더 이상 노출하지 않는다(요구사항: 이미지 레이아웃 그대로 반영). */}
                <div className="flex shrink-0 flex-col gap-1.5">
                  <span className="text-sm  text-muted">나의 투자</span>
                  <div className="flex flex-wrap items-baseline gap-3">
                    <span className="text-[32px] font-bold tracking-[-0.02em] text-ink">{won(holdTotal)}</span>
                    {/* 증감액 + 증감률 — 이 앱의 다른 화면과 동일하게 상승은 text-up, 하락은 text-down 으로 표시한다 */}
                    <span className={`text-lg font-bold ${gainPct >= 0 ? 'text-up' : 'text-down'}`}>
                      {gainAmount >= 0 ? '+' : ''}{gainAmount.toLocaleString('ko-KR')}원
                      ({gainPct >= 0 ? '+' : ''}{gainPct.toFixed(1)}%)
                    </span>
                  </div>
                </div>

                {/* 하단 — AI 제안, 최근 거래를 각각 컬럼 전체 폭으로 위아래로 붙여 쌓는다(좌우 2분할이 아니라 세로 스택).
                    폭을 전부 써야 3개 항목을 가로로 나란히(grid-cols-3) 배치했을 때 배지·종목명이 안 잘리고 읽힌다.
                    바깥 컨테이너가 self-start 라 이 블록도 콘텐츠 높이만큼만 차지하고, "나의 투자" 바로 아래부터
                    빈 공간 없이 두 박스가 gap-4 간격으로만 붙는다(shrink-0 이라 서로 눌리지 않는다). */}
                <div className="flex shrink-0 flex-col gap-4">
                  {/* AI의 리밸런싱 제안 — 카드를 클릭하면 "왜 지금인가요?" 사유 팝업(alertModal)을 연다.
                      가로 3칸(grid-cols-3)으로 배치하고, 항상 최신 3건만 보여준다.
                      "더 알아보기"는 박스 밖이 아니라 박스 안 우하단에 둔다(self-end, 마지막 자식). */}
                  <div className="flex flex-col gap-2 rounded-[16px] bg-surface p-4">
                    <span className="text-xs font-semibold text-[#3F5222]">✦ AI의 리밸런싱 제안</span>
                    {displayAlerts.length === 0 ? (
                      <p className="text-xs text-subtle">지금은 확인할 제안이 없어요.</p>
                    ) : (
                      <div className="grid grid-cols-3 gap-2">
                        {displayAlerts.slice(0, 3).map((a) => (
                          <button
                            key={a.id}
                            onClick={() => setAlertModalId(a.id)}
                            className="flex min-w-0 flex-col items-start gap-1.5 rounded-[10px] bg-canvas px-2.5 py-2.5 text-left"
                          >
                            <span className={`w-fit whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-bold ${ALERT_BADGE[a.kind]}`}>
                              {a.badge}
                            </span>
                            <span className="w-full truncate text-xs font-semibold text-ink">{a.stockName}</span>
                          </button>
                        ))}
                      </div>
                    )}
                    {/* AI 제안 전체 목록은 portfolio-detail 에 있어 "자세히"와 동일한 목적지로 보낸다 */}
                    <button onClick={onOpenDetail} className="self-end text-xs font-bold text-navy">
                      더 알아보기 →
                    </button>
                  </div>

                  {/* 최근 거래 — 가로 3칸(grid-cols-3)으로 배치하고, 항상 최신 3건만 보여준다.
                      "더 알아보기"는 마찬가지로 박스 안 우하단(self-end, 마지막 자식)에 둔다. */}
                  <div className="flex flex-col gap-2 rounded-[16px] bg-surface p-4">
                    <span className="text-xs font-semibold text-muted">최근 거래</span>
                    {recentTransactions.length === 0 ? (
                      <p className="text-xs text-subtle">아직 거래 내역이 없어요.</p>
                    ) : (
                      <div className="grid grid-cols-3 gap-2">
                        {recentTransactions.map((t) => (
                          <div key={t.id} className="flex min-w-0 flex-col gap-1.5 rounded-[10px] bg-canvas px-2.5 py-2.5">
                            <span className={`w-fit whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-bold ${TX_BADGE[t.type]}`}>
                              {t.type}
                            </span>
                            <span className="w-full truncate text-xs font-semibold text-ink">{t.stockName}</span>
                            <span className={`w-full truncate text-xs font-bold ${t.amount >= 0 ? 'text-up' : 'text-down'}`}>
                              {t.amount >= 0 ? '+' : ''}{t.amount.toLocaleString('ko-KR')}원
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                    {/* "자세히" 클릭 시 전체 거래 내역(transactions 화면)으로 이동한다 */}
                    <button onClick={() => onNavigate('transactions')} className="self-end text-xs font-bold text-navy">
                      더 알아보기 →
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>

    {/* 미설정 유저 안내 — 투자성향 진단/계좌 연동·입금/전략 선택 중 하나라도 비어있으면 배경 대시보드
        (목업 데이터 포함)를 블러 처리하고 중앙에 설정을 유도하는 모달을 띄운다. 대시보드 자체엔 블러
        클래스를 추가하지 않아도 backdrop-blur 가 이 오버레이 뒤에 있는 걸 그대로 블러해준다.
        닫기 버튼 없이 CTA 로만 빠져나갈 수 있게 해서 설정을 미루지 않도록 유도한다.
        다른 팝업(사유 모달·차트 확대, z-[700])보다 아래 레이어(z-40)에 둔다. */}
    {unconfiguredReason && (
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-8 backdrop-blur-md">
        <div className="flex w-full max-w-[480px] flex-col gap-6 rounded-card bg-surface p-10 text-center">
          <h2 className="text-2xl font-bold leading-9 tracking-[-0.02em]">
            {userName} 고객님! {UNCONFIGURED_COPY[unconfiguredReason].title}
          </h2>
          <p className="text-[17px] leading-7 text-[#3F4A43]">
            {UNCONFIGURED_COPY[unconfiguredReason].message}
          </p>
          <button
            onClick={() => {
              // 항목별로 목적지가 다르다 — 투자성향은 전용 Flow(startInvestorProfile)가 필요해 부모의
              // onStartRiskProfile 을 쓰고, 계좌/전략은 이미 있는 화면 전환(onNavigate)만으로 충분하다.
              switch (unconfiguredReason) {
                case 'risk':
                  onStartRiskProfile();
                  break;
                case 'account':
                  onNavigate('start');
                  break;
                case 'strategy':
                  onNavigate('strategy');
                  break;
              }
            }}
            className="rounded-field bg-lime py-5 text-lg font-bold text-navy"
          >
            {UNCONFIGURED_COPY[unconfiguredReason].cta}
          </button>
        </div>
      </div>
    )}

    {/* AI 제안 사유 팝업 — 좌하단 위젯의 카드를 클릭하면 왜 지금 손절/리밸런싱을 제안하는지 보여준다.
        h-screen overflow-hidden 인 페이지 루트 바깥(형제)에 둬서, 루트의 overflow-hidden 에 잘리지 않게 한다. */}
    {alertModal && (
      <div
        className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8"
        onClick={() => setAlertModalId(null)}
      >
        <div className="flex w-[480px] flex-col gap-5 rounded-card bg-surface p-9" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-start justify-between gap-6">
            <div className="flex flex-col gap-2">
              <span className={`w-fit rounded-full px-3 py-1.5 text-sm font-bold ${ALERT_BADGE[alertModal.kind]}`}>
                {alertModal.badge}
              </span>
              <h2 className="text-xl font-bold tracking-[-0.02em]">{alertModal.stockName} · 왜 지금인가요?</h2>
            </div>
            <button aria-label="닫기" onClick={() => setAlertModalId(null)} className="rounded-[9px] bg-canvas p-2 text-muted">
              <X size={16} />
            </button>
          </div>
          <p className="text-[15px] leading-6 text-[#3F4A43]">{alertModal.reason}</p>
          <div className="flex items-center gap-3 rounded-[14px] bg-[#F8FCEE] px-6 py-5">
            <span className="shrink-0 text-sm font-semibold text-[#3F5222]">AI 제안</span>
            <span className="text-sm font-semibold text-ink">{alertModal.action}</span>
          </div>
        </div>
      </div>
    )}

    {/* 차트 "크게 보기" 팝업 — 현재 tab 이 가리키는 차트를 같은 렌더 함수로 훨씬 큰 사이즈로 다시 그린다.
        요약(도넛)은 정사각형이라 폭을 좁게, 자산 변화/종목별 기여는 가로로 넓은 차트라 폭을 넓게 잡는다.
        마찬가지로 페이지 루트 바깥(형제)에 둬서 h-screen overflow-hidden 에 잘리지 않게 한다. */}
    {isChartZoomOpen && (
      <div
        className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8"
        onClick={() => setIsChartZoomOpen(false)}
      >
        <div
          className={`flex flex-col gap-6 rounded-card bg-surface p-10 ${tab === 'weight' ? '' : 'w-[720px]'}`}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between gap-6">
            <h2 className="text-xl font-bold tracking-[-0.02em]">
              {tab === 'weight' ? '포트폴리오 배분' : tab === 'trend' ? '자산 변화 추이' : '종목별 기여도'}
            </h2>
            <button aria-label="닫기" onClick={() => setIsChartZoomOpen(false)} className="rounded-[9px] bg-canvas p-2 text-muted">
              <X size={16} />
            </button>
          </div>
          {tab === 'weight' && renderDonutChart('h-[560px] w-[560px]')}
          {tab === 'trend' && renderTrendChart('h-[460px]')}
          {tab === 'contribution' && renderContributionChart('h-[460px]')}
        </div>
      </div>
    )}
    </>
  );
}

function Insight({ children, compact }: { children: React.ReactNode; compact?: boolean }) {
  return (
    <div className={`flex shrink-0 items-start gap-3 rounded-[16px] bg-[#F8FCEE] ${compact ? 'px-6 py-3' : 'px-8 py-6'}`}>
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-lime text-sm text-navy">✦</div>
      <p className="pt-0.5 text-sm leading-6 text-[#3F4A43]">{children}</p>
    </div>
  );
}
