import { useEffect, useState } from "react";
import Header from "../components/Header";
import TermsModal from "../components/TermsModal";
import { type OperationMode } from "../data/fees";
import { OPERATING_MODES } from "../data/operatingModes";
import {
  getInvestmentTermsApi,
  type InvestmentTermResponse,
  type SignupPayload,
  type StrategyResponse,
} from "../lib/backendApi";
import { won } from "../lib/validation";
import type { Screen } from "../types";

interface Props {
  userName: string;
  strategy: StrategyResponse;
  amount: number;
  mode: OperationMode;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
  token: string;
  /** 필수 확인 전체 동의 완료 — 확인한 약관의 code/version을 함께 전달한다. */
  onComplete: (agreements: SignupPayload["agreements"]) => void;
}

export default function InvestTerms({
  userName,
  strategy,
  amount,
  mode,
  token,
  onNavigate,
  onBack,
  onComplete,
}: Props) {
  const [terms, setTerms] = useState<InvestmentTermResponse[]>([]);
  const [agreed, setAgreed] = useState<Record<string, boolean>>({});
  const [modal, setModal] = useState<InvestmentTermResponse | null>(null);

  useEffect(() => {
    getInvestmentTermsApi(strategy.id, token).then((loaded) => {
      const required = loaded.filter((term) => term.is_required);
      setTerms(required);
      setAgreed(
        Object.fromEntries(required.map((term) => [term.term_code, false])),
      );
    });
  }, [strategy.id, token]);

  const allAgreed =
    terms.length > 0 && terms.every((term) => agreed[term.term_code]);
  const toggleAll = () => {
    const next = !allAgreed;
    setAgreed(Object.fromEntries(terms.map((term) => [term.term_code, next])));
  };
  const toggleOne = (code: string) =>
    setAgreed((prev) => ({ ...prev, [code]: !prev[code] }));

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[720px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <button
              onClick={onBack}
              className="self-start text-base font-semibold text-muted"
            >
              ← 이전으로
            </button>
            <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">
              투자를 시작하기 전에 확인해주세요
            </h1>
          </section>

          <section className="flex flex-col gap-3 rounded-card bg-surface p-9">
            <div className="flex items-center justify-between">
              <span className="text-[20px] font-bold tracking-[-0.02em]">
                {strategy.name}
              </span>
              <span className="text-base text-muted">
                {OPERATING_MODES[mode].label}
              </span>
            </div>
            <span className="text-lg text-muted">
              투자 예정 금액 <b className="text-ink">{won(amount)}</b>
            </span>
          </section>

          <section className="flex flex-col gap-3 rounded-card bg-surface p-9">
            <button
              onClick={toggleAll}
              className="flex items-center gap-3 pb-2 text-left"
            >
              <Check on={allAgreed} />
              <span className="text-[17px] font-bold">필수 약관 모두 동의</span>
            </button>
            <div className="h-px bg-line" />

            {terms.map((term) => (
              <AgreementRow
                key={term.term_code}
                checked={agreed[term.term_code] ?? false}
                onToggle={() => toggleOne(term.term_code)}
                label={term.title}
                onView={() => setModal(term)}
              />
            ))}
          </section>

          <button
            onClick={() =>
              onComplete(
                terms.map((term) => ({
                  term_code: term.term_code,
                  version: term.version,
                  agreed: agreed[term.term_code] === true,
                })),
              )
            }
            disabled={!allAgreed}
            className="rounded-field py-5 text-[19px] font-bold transition-colors disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
          >
            동의하고 계속하기 →
          </button>
        </div>
      </main>

      {modal && (
        <TermsModal
          title={modal.title}
          body={
            modal.content_reference ??
            "약관 전문은 백엔드 약관 catalog의 현재 버전으로 확인했습니다."
          }
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}

function AgreementRow({
  checked,
  onToggle,
  label,
  onView,
}: {
  checked: boolean;
  onToggle: () => void;
  label: string;
  onView: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <button
        onClick={onToggle}
        className="flex flex-1 items-center gap-3 py-1 text-left"
      >
        <Check on={checked} />
        <span className="text-[16px] leading-[24px] text-[#3F4A43]">
          {label}
        </span>
      </button>
      <button
        onClick={onView}
        className="shrink-0 text-sm text-subtle underline"
      >
        보기 &gt;
      </button>
    </div>
  );
}

function Check({ on }: { on: boolean }) {
  return (
    <span
      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
        on ? "bg-lime text-navy" : "bg-[#F0F2ED] text-white"
      }`}
    >
      ✓
    </span>
  );
}
