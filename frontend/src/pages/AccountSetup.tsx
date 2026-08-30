import { useState } from "react";
import Header from "../components/Header";
import type { OperationMode } from "../data/fees";
import {
  OPERATING_MODES,
  OPERATING_MODE_ORDER,
} from "../data/operatingModes";
import type { Screen } from "../types";

interface Props {
  userName: string;
  initialMode: OperationMode;
  onNavigate: (screen: Screen) => void;
  onBack: () => void;
  onComplete: (mode: OperationMode) => Promise<void>;
}

export default function AccountSetup({
  userName,
  initialMode,
  onNavigate,
  onBack,
  onComplete,
}: Props) {
  const [mode, setMode] = useState<OperationMode>(initialMode);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      await onComplete(mode);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "계좌를 준비하지 못했어요. 잠시 후 다시 시도해주세요.",
      );
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />
      <main className="flex flex-col items-center px-6 pb-24 pt-8 sm:px-16">
        <div className="flex w-full max-w-[760px] flex-col gap-9">
          <section className="flex flex-col gap-4">
            <button
              onClick={onBack}
              className="self-start text-base font-semibold text-muted"
            >
              ← 포트폴리오로
            </button>
            <span className="text-sm font-bold text-muted">계좌 준비</span>
            <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">
              전략보다 계좌를 먼저 준비할 수 있어요
            </h1>
            <p className="text-lg leading-8 text-muted">
              운용방식에 맞는 SeSAC 가상계좌를 만들어요. 전략 선택과 투자
              시작은 입금 후에 별도로 진행할 수 있어요.
            </p>
          </section>

          <section className="grid gap-4 sm:grid-cols-2">
            {OPERATING_MODE_ORDER.map((item) => {
              const info = OPERATING_MODES[item];
              const selected = item === mode;
              return (
                <button
                  key={item}
                  type="button"
                  onClick={() => setMode(item)}
                  aria-pressed={selected}
                  className={`flex flex-col gap-4 rounded-card p-7 text-left shadow-sm transition ${
                    selected
                      ? "bg-navy text-white ring-4 ring-lime"
                      : "bg-surface text-ink"
                  }`}
                >
                  <div className="flex w-full items-center justify-between gap-3">
                    <strong className="text-xl">{info.label}</strong>
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-bold ${
                        selected ? "bg-lime text-navy" : "bg-canvas text-muted"
                      }`}
                    >
                      {info.recommendation}
                    </span>
                  </div>
                  <p
                    className={`text-sm leading-6 ${selected ? "text-white" : "text-muted"}`}
                  >
                    {info.description}
                  </p>
                </button>
              );
            })}
          </section>

          {error && (
            <p className="rounded-field bg-surface-soft px-5 py-4 text-sm font-semibold text-down" role="alert">
              {error}
            </p>
          )}

          <button
            onClick={submit}
            disabled={isSubmitting}
            className="rounded-field bg-lime py-5 text-lg font-bold text-navy disabled:opacity-60"
          >
            {isSubmitting ? "계좌를 준비하고 있어요..." : "계좌 준비하기 →"}
          </button>
        </div>
      </main>
    </div>
  );
}
