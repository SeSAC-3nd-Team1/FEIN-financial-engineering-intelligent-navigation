import { useMemo, useRef, useState } from "react";
import Header from "../components/Header";
import type { OperationMode } from "../data/fees";
import { OPERATING_MODES } from "../data/operatingModes";
import { useTradingData } from "../hooks/useTradingData";
import type { AccountResponse } from "../lib/backendApi";
import { digitsOnly, won } from "../lib/validation";
import type { Screen } from "../types";

const PRESETS = [100_000, 500_000, 1_000_000, 5_000_000];

interface Props {
  userName: string;
  mode: OperationMode;
  account: AccountResponse | null;
  onNavigate: (screen: Screen) => void;
  onBack: () => void;
  onDeposit: (amount: number, idempotencyKey: string) => Promise<void>;
  onDefer: () => void;
}

export default function AccountDeposit({
  userName,
  mode,
  account,
  onNavigate,
  onBack,
  onDeposit,
  onDefer,
}: Props) {
  useTradingData();
  const [amountText, setAmountText] = useState("500000");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pendingRequest = useRef<{ amount: number; key: string } | null>(null);
  const amount = useMemo(() => Number(amountText || 0), [amountText]);

  const submit = async () => {
    if (!account || amount <= 0) return;
    setIsSubmitting(true);
    setError(null);
    try {
      if (!pendingRequest.current || pendingRequest.current.amount !== amount) {
        pendingRequest.current = {
          amount,
          key: `account-cash-${crypto.randomUUID()}`,
        };
      }
      await onDeposit(amount, pendingRequest.current.key);
      pendingRequest.current = null;
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "입금하지 못했어요. 잠시 후 다시 시도해주세요.",
      );
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />
      <main className="flex flex-col items-center px-6 pb-24 pt-8 sm:px-16">
        <div className="flex w-full max-w-[720px] flex-col gap-8">
          <section className="flex flex-col gap-4">
            <button
              onClick={onBack}
              className="self-start text-base font-semibold text-muted"
            >
              ← 계좌 설정으로
            </button>
            <span className="text-sm font-bold text-muted">현금 입금</span>
            <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">
              투자할 현금을 먼저 넣어둘 수 있어요
            </h1>
            <p className="text-lg leading-8 text-muted">
              입금은 전략을 선택하거나 주문을 만들지 않아요. 현금으로 보관한 뒤
              원할 때 전략을 선택해 투자를 시작하세요.
            </p>
          </section>

          <section className="flex flex-col gap-5 rounded-card bg-surface p-8">
            <div className="flex items-center justify-between gap-4">
              <span className="text-sm text-muted">준비된 계좌</span>
              <strong>{account?.account_name ?? "계좌를 확인하고 있어요"}</strong>
            </div>
            <div className="flex items-center justify-between gap-4 border-t border-line pt-5">
              <span className="text-sm text-muted">운용방식</span>
              <strong>{OPERATING_MODES[mode].label}</strong>
            </div>
            <div className="flex items-center justify-between gap-4 border-t border-line pt-5">
              <span className="text-sm text-muted">현재 현금 잔액</span>
              <strong className="text-xl">
                {won(Number(account?.cash_balance ?? 0))}
              </strong>
            </div>
          </section>

          <section className="flex flex-col gap-4 rounded-card bg-surface p-8">
            <label htmlFor="account-deposit-amount" className="text-lg font-bold">
              입금 금액
            </label>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {PRESETS.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => setAmountText(String(preset))}
                  className="rounded-field bg-surface-soft px-3 py-3 text-sm font-semibold text-ink"
                >
                  {won(preset)}
                </button>
              ))}
            </div>
            <div className="flex items-center rounded-field bg-canvas px-5 py-4">
              <input
                id="account-deposit-amount"
                inputMode="numeric"
                value={amountText}
                onChange={(event) =>
                  setAmountText(digitsOnly(event.target.value, 9))
                }
                className="min-w-0 flex-1 bg-transparent text-right text-2xl font-bold outline-none"
                aria-describedby="account-deposit-help"
              />
              <span className="ml-2 font-bold">원</span>
            </div>
            <p id="account-deposit-help" className="text-sm text-muted">
              1회 최대 1억원까지 입금할 수 있어요.
            </p>
          </section>

          {error && (
            <p className="rounded-field bg-surface-soft px-5 py-4 text-sm font-semibold text-down" role="alert">
              {error}
            </p>
          )}

          <div className="flex flex-col gap-3">
            <button
              onClick={submit}
              disabled={!account || amount <= 0 || amount > 100_000_000 || isSubmitting}
              className="rounded-field bg-lime py-5 text-lg font-bold text-navy disabled:opacity-60"
            >
              {isSubmitting ? "입금 처리 중..." : `${won(amount)} 입금하기 →`}
            </button>
            <button
              onClick={onDefer}
              disabled={isSubmitting}
              className="py-2 text-base font-semibold text-muted underline"
            >
              지금은 입금하지 않고 포트폴리오 보기
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
