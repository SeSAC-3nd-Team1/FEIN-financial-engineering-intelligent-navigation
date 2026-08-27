import { useMemo } from 'react';
import Header from '../components/Header';
import { getDisplayTransactions } from '../lib/transactions';
import { useTradingData } from '../hooks/useTradingData';
import { useTradingStore } from '../store/tradingStore';
import type { Screen, TransactionRecord } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  onSelectTransaction: (id: string) => void;
  onBack: () => void;
}

const TX_BADGE: Record<TransactionRecord['type'], string> = {
  '매수': 'bg-[#F4F6F1] text-[#3F4A43]',
  '매도': 'bg-[#EAF2FD] text-down',
  '리밸런싱': 'bg-[#FCF3E4] text-warn',
  '배당': 'bg-[#F8FCEE] text-[#3F5222]',
};

/** `/transactions` — 전체 거래 내역. 실 체결(executions)이 있으면 그걸, 없으면 목업으로 대체한다. */
export default function TransactionHistory({ userName, onNavigate, onSelectTransaction, onBack }: Props) {
  useTradingData();
  const executions = useTradingStore((state) => state.executions);
  // 계좌 자체가 없다고 "확인된" 상태(404)일 때만 목업을 쓴다. account !== null 은 로딩 직후/조회
  // 실패 상태에서 account 가 아직 null이라 실계좌 사용자에게도 mock 거래내역이 노출될 수 있다.
  const accountMissing = useTradingStore((state) => state.accountMissing);
  const transactions = useMemo(() => getDisplayTransactions(executions, !accountMissing), [executions, accountMissing]);

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <button onClick={onBack} className="self-start text-[15px] text-muted">← 돌아가기</button>

          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">거래 내역</span>
            <h1 className="text-[38px] font-bold leading-[52px] tracking-[-0.03em]">전체 거래 내역</h1>
            <span className="text-[17px] text-subtle">총 {transactions.length}건</span>
          </section>

          <section className="flex flex-col rounded-card bg-surface p-6">
            {transactions.length === 0 ? (
              <p className="px-6 py-10 text-center text-[17px] text-subtle">아직 거래 내역이 없어요.</p>
            ) : (
              transactions.map((t) => (
                <button
                  key={t.id}
                  onClick={() => onSelectTransaction(t.id)}
                  className="flex items-center gap-6 border-b border-line px-6 py-5 text-left last:border-0 hover:bg-canvas"
                >
                  <span className="w-24 shrink-0 text-[14px] text-subtle">{t.date}</span>
                  <span className={`w-[76px] shrink-0 rounded-full px-3 py-1.5 text-center text-sm font-bold ${TX_BADGE[t.type]}`}>
                    {t.type}
                  </span>
                  <div className="flex flex-1 flex-col gap-0.5">
                    <span className="text-[17px] font-semibold text-[#3F4A43]">{t.stockName}</span>
                    <span className="text-[14px] text-subtle">{t.note}</span>
                  </div>
                  <span className={`shrink-0 text-[16px] font-bold ${t.amount >= 0 ? 'text-up' : 'text-down'}`}>
                    {t.amount >= 0 ? '+' : ''}{t.amount.toLocaleString('ko-KR')}원
                  </span>
                </button>
              ))
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
