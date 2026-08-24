import { useState } from 'react';
import Header from '../components/Header';
import InvestmentProgress from '../components/InvestmentProgress';
import type { OperationMode } from '../data/fees';
import { won } from '../lib/validation';
import type { SesacAccount } from '../store/investmentStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  strategyName: string;
  amount: number;
  mode: OperationMode;
  account: SesacAccount;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
  /** "투자 시작하기" — 실제 계좌 생성/전략 반영 후 Portfolio로 이동한다 */
  onConfirm: () => Promise<void>;
}

const MODE_LABEL: Record<OperationMode, string> = { manual: '확인하고 실행', auto: '자동으로 운용' };

export default function InvestConfirm({
  userName, strategyName, amount, mode, account, onNavigate, onBack, onConfirm,
}: Props) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const maskedAccount = `••••${account.accountNumber.slice(-4)}`;

  const handleConfirm = async () => {
    if (submitting) return;
    setSubmitting(true);
    setError('');
    try {
      await onConfirm();
    } catch (e) {
      setError(e instanceof Error ? e.message : '투자를 시작하지 못했습니다. 잠시 후 다시 시도해주세요.');
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[720px] flex-col gap-10">
          <section className="flex flex-col gap-6">
            <button onClick={onBack} className="self-start text-base font-semibold text-muted">← 이전으로</button>
            <InvestmentProgress current="confirm" />
            <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">이대로 투자를 시작할까요?</h1>
            <p className="text-lg leading-[30px] text-muted">
              투자 시작 후에는 실제 자금으로 매매가 진행돼요. 아래 내용을 한 번 더 확인해주세요.
            </p>
          </section>

          <section className="flex flex-col gap-5 rounded-card bg-surface p-9">
            <div className="flex items-center justify-between">
              <span className="text-[20px] font-bold tracking-[-0.02em]">{strategyName}</span>
              <span className="text-base text-muted">{MODE_LABEL[mode]}</span>
            </div>
            <div className="h-px bg-line" />
            <div className="flex items-center justify-between">
              <span className="text-base text-muted">투자금액</span>
              <span className="text-[22px] font-bold tracking-[-0.02em] text-ink">{won(amount)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-base text-muted">SeSAC증권</span>
              <span className="text-lg font-semibold text-ink">{maskedAccount}</span>
            </div>
          </section>

          <div className="flex items-start gap-3 rounded-[14px] bg-[#FFF6EC] px-5 py-4">
            <p className="text-[15px] leading-[24px] text-[#7A5A1E]">
              투자 결과에 따라 원금의 일부 또는 전부 손실이 발생할 수 있습니다.
            </p>
          </div>

          <button
            onClick={() => void handleConfirm()}
            disabled={submitting}
            className="rounded-field bg-lime py-5 text-[19px] font-bold text-navy disabled:opacity-60"
          >
            {submitting ? '투자 시작 중...' : '투자 시작하기 →'}
          </button>
          {error && <p className="text-center text-sm text-up">{error}</p>}
        </div>
      </main>
    </div>
  );
}
