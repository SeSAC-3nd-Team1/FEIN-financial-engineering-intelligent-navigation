import { useMemo, useState } from 'react';
import { ChevronDown, ChevronsUpDown, ChevronUp, X } from 'lucide-react';
import Header from '../components/Header';
import { AI_ALERTS, ALL_HOLDINGS as MOCK_HOLDINGS, STOCK_INFO } from '../data/holdings';
import { useTradingData } from '../hooks/useTradingData';
import { won } from '../lib/validation';
import { useTradingStore } from '../store/tradingStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  onSelectStock: (index: number) => void;
  onBack: () => void;
}

/** AI 제안 종류별 배지 색 — PortfolioDetail 의 보유 종목 표와 동일한 배색을 공유한다 */
const ALERT_BADGE: Record<'손절' | '리밸런싱', string> = {
  '손절': 'bg-[#FBEAEA] text-up',
  '리밸런싱': 'bg-[#FCF3E4] text-warn',
};

/** 보유 종목 표 — 클릭으로 오름/내림차순 토글되는 정렬 열 */
type SortKey = 'name' | 'pct' | 'principal' | 'returnRate';
const HOLDINGS_COLUMNS: { key: SortKey; label: string; align: 'left' | 'right' }[] = [
  { key: 'name', label: '종목명', align: 'left' },
  { key: 'pct', label: '비율', align: 'right' },
  { key: 'principal', label: '투자 원금', align: 'right' },
  { key: 'returnRate', label: '원금 대비 수익률', align: 'right' },
];

/** `/all-holdings` — 보유 종목 전체 목록. PortfolioDetail "보유 종목"의 "전체 종목 보기"에서 진입한다. */
export default function AllHoldings({ userName, onNavigate, onSelectStock, onBack }: Props) {
  useTradingData();
  const portfolio = useTradingStore((state) => state.portfolio);

  // 실 계좌가 있으면 포지션을, 없으면 목업 20종목을 쓴다 — PortfolioDetail 과 동일한 대체 규칙.
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

  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
  };
  const sortedHoldings = useMemo(() => {
    if (!sortKey) return ALL_HOLDINGS;
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...ALL_HOLDINGS].sort((a, b) =>
      sortKey === 'name' ? a.name.localeCompare(b.name) * dir : (a[sortKey] - b[sortKey]) * dir
    );
  }, [ALL_HOLDINGS, sortKey, sortDir]);

  // 표의 배지 클릭 시 "왜 지금인가요?" 사유 모달만 연다 — PortfolioDetail 의 보유 종목 표와 동일한 동작.
  const [alertModalId, setAlertModalId] = useState<string | null>(null);
  const alertModal = AI_ALERTS.find((a) => a.id === alertModalId) ?? null;

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <button onClick={onBack} className="self-start text-[15px] text-muted">← 돌아가기</button>

          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">보유 종목</span>
            <h1 className="text-[38px] font-bold leading-[52px] tracking-[-0.03em]">전체 {ALL_HOLDINGS.length}개 종목</h1>
            <span className="text-[17px] text-subtle">종목을 누르면 상세 정보를 볼 수 있어요</span>
          </section>

          <section className="rounded-card bg-surface p-12">
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
                  {sortedHoldings.map((h) => {
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
          </section>
        </div>
      </main>

      {/* AI 제안 사유 모달 — 표의 배지를 누르면 근거와 제안 조치를 보여준다 */}
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
    </div>
  );
}
