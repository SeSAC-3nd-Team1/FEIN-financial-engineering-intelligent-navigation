import { useState } from 'react';
import Header from '../components/Header';
import InvestmentProgress from '../components/InvestmentProgress';
import type { OperationMode } from '../data/fees';
import { OPERATING_MODES } from '../data/operatingModes';
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
  /** 입금 완료 → 최종 확인 단계로. 이미 보유한 잔액을 제외한 부족분(shortfall)을 인자로 넘긴다 */
  onDeposit: (shortfall: number) => void;
  /** "나중에 입금할게요" — DEPOSIT_PENDING으로 저장하고 홈으로 나간다 */
  onDeferDeposit: () => void;
}

export default function InvestDeposit({
  userName, strategyName, amount, mode, account, onNavigate, onBack, onDeposit, onDeferDeposit,
}: Props) {
  const [depositing, setDepositing] = useState(false);
  const maskedAccount = `••••${account.accountNumber.slice(-4)}`;
  // 재투자 등으로 계좌에 이미 잔액이 있는 경우, 목표 금액 전체가 아니라 부족한 만큼만 입금하면 된다
  const hasExistingBalance = account.balance > 0;
  const shortfall = Math.max(0, amount - account.balance);

  const handleDeposit = () => {
    setDepositing(true);
    // PoC Mock — 실제 이체 연동 전까지 짧은 처리 지연만 흉내낸다
    setTimeout(() => onDeposit(shortfall), 500);
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[720px] flex-col gap-10">
          <section className="flex flex-col gap-6">
            <button onClick={onBack} className="self-start text-base font-semibold text-muted">← 이전으로</button>
            <InvestmentProgress current="deposit" />
            <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">투자 시작까지 한 단계 남았어요</h1>
          </section>

          <section className="flex gap-6 rounded-card bg-[#F8FCEE] p-9">
            <img src="/character-recommend.png" alt="물방개" className="h-[100px] w-[100px] shrink-0 object-contain" />
            <div className="flex flex-1 flex-col justify-center gap-2">
              <span className="text-[15px] font-semibold text-[#3F5222]">물방개가 다음 단계를 알려드릴게요</span>
              <p className="text-lg leading-[28px] text-ink">
                계좌 연결까지 완료했어요. 이제 투자금을 입금하면<br />선택한 전략으로 시작할 수 있어요.
              </p>
            </div>
          </section>

          <section className="flex flex-col gap-5 rounded-card bg-surface p-9">
            <div className="flex items-center justify-between">
              <span className="text-[20px] font-bold tracking-[-0.02em]">{strategyName}</span>
              <span className="text-base text-muted">{OPERATING_MODES[mode].label}</span>
            </div>
            <div className="h-px bg-line" />
            <div className="flex items-center justify-between">
              <span className="text-base text-muted">투자 예정 금액</span>
              <span className="text-[22px] font-bold tracking-[-0.02em] text-ink">{won(amount)}</span>
            </div>
            {hasExistingBalance && (
              <div className="flex items-center justify-between">
                <span className="text-base text-muted">현재 보유 잔액</span>
                <span className="text-lg font-semibold text-ink">{won(account.balance)}</span>
              </div>
            )}
            <div className="flex items-center justify-between">
              <span className="text-base text-muted">연결 계좌</span>
              <span className="text-lg font-semibold text-ink">SeSAC증권 {maskedAccount}</span>
            </div>
          </section>

          <div className="flex flex-col gap-3">
            <button
              onClick={handleDeposit}
              disabled={depositing}
              className="rounded-field bg-lime py-5 text-[19px] font-bold text-navy disabled:opacity-60"
            >
              {depositing ? '입금 처리 중...' : `${won(shortfall)} 입금하기 →`}
            </button>
            <button onClick={onDeferDeposit} disabled={depositing} className="py-2 text-base font-semibold text-muted underline">
              나중에 입금할게요
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
