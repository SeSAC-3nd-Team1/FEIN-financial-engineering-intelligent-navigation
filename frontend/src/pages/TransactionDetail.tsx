import { useMemo } from 'react';
import Header from '../components/Header';
import { getDisplayTransactions } from '../lib/transactions';
import { useTradingData } from '../hooks/useTradingData';
import PortfolioDataState from '../components/PortfolioDataState';
import { useTradingRetry } from '../hooks/useTradingRetry';
import { useTradingStore } from '../store/tradingStore';
import type { Screen, TransactionRecord } from '../types';

interface Props {
  transactionId: string;
  /** 이 화면에 진입한 경로 — PortfolioDetail "최근 거래" 3건에서 왔으면 'portfolio-detail',
   *  전체 거래 내역에서 왔으면 'transactions'. onBack 이 실제로 돌아가는 목적지와
   *  버튼 문구가 항상 일치하도록 이 값으로 라벨을 고른다. */
  backTarget: Screen;
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
}

const TX_BADGE: Record<TransactionRecord['type'], string> = {
  '매수': 'bg-[#F4F6F1] text-[#3F4A43]',
  '매도': 'bg-[#EAF2FD] text-down',
  '리밸런싱': 'bg-[#FCF3E4] text-warn',
  '배당': 'bg-[#F8FCEE] text-[#3F5222]',
};

const BACK_LABEL: Partial<Record<Screen, string>> = {
  'transactions': '거래 내역으로 돌아가기',
  'portfolio-detail': '포트폴리오 상세로 돌아가기',
};

/** `/transactions/:id` — 백엔드 체결 내역에서 거래 1건을 표시한다. */
export default function TransactionDetail({ transactionId, backTarget, userName, onNavigate, onBack }: Props) {
  useTradingData();
  const executions = useTradingStore((state) => state.executions);
  const loading = useTradingStore((state) => state.isLoading);
  const accountMissing = useTradingStore((state) => state.accountMissing);
  const error = useTradingStore((state) => state.error);
  const retry = useTradingRetry();
  const transactions = useMemo(() => getDisplayTransactions(executions), [executions]);

  const t = transactions.find((item) => item.id === transactionId);
  const backLabel = BACK_LABEL[backTarget] ?? '이전으로 돌아가기';

  return (
    <PortfolioDataState
      userName={userName}
      onNavigate={onNavigate}
      loading={loading}
      accountMissing={accountMissing}
      error={error}
      onRetry={retry}
    >
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[640px] flex-col gap-10">
          <button onClick={onBack} className="self-start text-[15px] text-muted">← {backLabel}</button>

          {!t ? (
            <p className="py-16 text-center text-[17px] text-subtle">거래 내역을 찾을 수 없어요.</p>
          ) : (
            <>
              <section className="flex flex-col gap-4">
                <span className={`w-fit rounded-full px-3 py-1.5 text-sm font-bold ${TX_BADGE[t.type]}`}>{t.type}</span>
                <h1 className="text-[34px] font-bold leading-[46px] tracking-[-0.03em]">{t.stockName}</h1>
                <span className={`text-[28px] font-bold tracking-[-0.03em] ${t.amount >= 0 ? 'text-up' : 'text-down'}`}>
                  {t.amount >= 0 ? '+' : ''}{t.amount.toLocaleString('ko-KR')}원
                </span>
              </section>

              <section className="flex flex-col gap-0 rounded-card bg-surface p-2">
                <Row label="거래일시" value={t.date} />
                <Row label="상태" value={t.status} />
                <Row label="수량" value={t.quantity > 0 ? `${t.quantity}주` : '-'} />
                <Row label="체결 단가" value={t.price > 0 ? `${t.price.toLocaleString('ko-KR')}원` : '-'} />
                <Row label="수수료" value={`${t.fee.toLocaleString('ko-KR')}원`} />
                <Row label="메모" value={t.note} last />
              </section>
            </>
          )}
                </div>
      </main>
    </div>
    </PortfolioDataState>
  );
}

function Row({ label, value, last }: { label: string; value: string; last?: boolean }) {
  return (
    <div className={`flex items-center justify-between px-6 py-5 ${last ? '' : 'border-b border-line'}`}>
      <span className="text-[15px] text-muted">{label}</span>
      <span className="text-[16px] font-semibold text-ink">{value}</span>
    </div>
  );
}
