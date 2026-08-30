import { CheckCircle2 } from 'lucide-react';
import Header from '../components/Header';
import { won } from '../lib/validation';
import type { FundOperationResponse } from '../lib/backendApi';
import type { Screen } from '../types';

interface Props {
  kind: 'deposit' | 'withdraw';
  operation: FundOperationResponse;
  userName: string;
  onNavigate: (screen: Screen) => void;
  onDone: () => void;
}

export default function FundOperationResult({ kind, operation, userName, onNavigate, onDone }: Props) {
  const isDeposit = kind === 'deposit';
  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />
      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[720px] flex-col gap-10">
          <section className="flex flex-col items-center gap-4 rounded-card bg-surface px-10 py-16 text-center">
            <CheckCircle2 size={52} className="text-lime" />
            <h1 className="text-[36px] font-bold tracking-[-0.035em]">
              {isDeposit ? '추가 투자가 완료됐어요' : '출금이 완료됐어요'}
            </h1>
            <p className="text-lg text-muted">
              {won(Number(operation.executed_amount))}이(가) 처리됐어요.
            </p>
          </section>
          <section className="flex flex-col gap-4 rounded-card bg-surface p-8">
            <div className="flex justify-between text-base"><span className="text-muted">현재 총 자산</span><strong>{won(Number(operation.portfolio.total_assets))}</strong></div>
            <div className="flex justify-between text-base"><span className="text-muted">출금 가능 금액</span><strong>{won(Number(operation.portfolio.withdrawable_amount))}</strong></div>
            <div className="flex justify-between text-base"><span className="text-muted">처리된 거래</span><strong>{operation.trades.length}건</strong></div>
          </section>
          <button onClick={onDone} className="rounded-field bg-navy py-4 text-base font-bold text-white">나의 포트폴리오로 돌아가기</button>
        </div>
      </main>
    </div>
  );
}
