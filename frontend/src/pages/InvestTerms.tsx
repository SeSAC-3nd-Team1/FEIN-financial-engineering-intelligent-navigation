import { useState } from 'react';
import Header from '../components/Header';
import TermsModal from '../components/TermsModal';
import { estimateAnnualFee, type OperationMode } from '../data/fees';
import { OPERATING_MODES } from '../data/operatingModes';
import type { StrategyResponse } from '../lib/backendApi';
import { won } from '../lib/validation';
import type { Screen } from '../types';

interface Props {
  userName: string;
  strategy: StrategyResponse;
  amount: number;
  mode: OperationMode;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
  /** 필수 확인 전체 동의 완료 — App.tsx가 다음 단계(계좌 준비/입금/최종 확인)로 라우팅한다 */
  onComplete: () => void;
}

type RequiredKey = 'product' | 'service' | 'privacy' | 'riskNotice';

const SERVICE_TERMS_BODY =
  '제1조 (목적)\n본 약관은 FE!N이 제공하는 투자 서비스(전략 기반 포트폴리오 구성 및 SeSAC증권 연계 매매)의 이용과 관련한 회사와 이용자 간의 권리·의무를 규정합니다.\n\n제2조 (서비스 내용)\nFE!N은 이용자가 선택한 투자 전략에 따라 포트폴리오를 구성하고, SeSAC증권 계좌를 통해 매매를 실행하거나 자동으로 운용합니다.\n\n제3조 (투자 판단 및 책임)\nFE!N과 물방개가 제공하는 정보는 투자 판단을 돕기 위한 참고 정보이며, 최종 투자 결정과 그 결과에 대한 책임은 이용자 본인에게 있습니다.';

const PRIVACY_TERMS_BODY =
  '수집·이용 목적: 투자 서비스 제공(포트폴리오 구성, 매매 실행, 리밸런싱), SeSAC증권 계좌 연계\n수집·이용 항목: 투자성향 진단 결과, 선택 전략, 투자 금액·운용 방식, SeSAC증권 계좌 정보, 거래내역\n보유 및 이용기간: 서비스 이용 종료 또는 회원 탈퇴 시까지\n\n동의를 거부할 권리가 있으나, 필수 동의 사항이므로 거부 시 투자 서비스 이용이 제한됩니다.';

const RISK_LABEL: Record<string, string> = { LOW: '낮음', MEDIUM: '보통', HIGH: '높음' };
const REBALANCE_LABEL: Record<string, string> = {
  WEEKLY: '주 1회', MONTHLY: '월 1회', QUARTERLY: '분기 1회', YEARLY: '연 1회',
};

export default function InvestTerms({ userName, strategy, amount, mode, onNavigate, onBack, onComplete }: Props) {
  const [agreed, setAgreed] = useState<Record<RequiredKey, boolean>>({
    product: false, service: false, privacy: false, riskNotice: false,
  });
  const [modal, setModal] = useState<'product' | 'service' | 'privacy' | null>(null);

  const allAgreed = Object.values(agreed).every(Boolean);
  const toggleAll = () => {
    const next = !allAgreed;
    setAgreed({ product: next, service: next, privacy: next, riskNotice: next });
  };
  const toggleOne = (key: RequiredKey) => setAgreed((prev) => ({ ...prev, [key]: !prev[key] }));

  const feeRate = OPERATING_MODES[mode].feeRate;
  const feeAmount = estimateAnnualFee(amount, mode);
  const productBody =
    `${strategy.name}은 ${strategy.description}\n\n` +
    `위험도: ${RISK_LABEL[strategy.risk_level] ?? strategy.risk_level}\n` +
    `리밸런싱 주기: ${REBALANCE_LABEL[strategy.rebalance_cycle] ?? strategy.rebalance_cycle}\n\n` +
    `이용 수수료: 연 ${(feeRate * 100).toFixed(1)}% (${OPERATING_MODES[mode].label} 기준, ${(amount / 10_000).toLocaleString('ko-KR')}만원 투자 시 연 약 ${won(feeAmount)})\n\n` +
    '투자 전 상세 화면의 실제 백테스트 결과와 위험 안내를 확인해주세요. 실제 수수료는 잔고와 이용 기간 등에 따라 달라질 수 있어요.';

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[720px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <button onClick={onBack} className="self-start text-base font-semibold text-muted">← 이전으로</button>
            <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">투자를 시작하기 전에 확인해주세요</h1>
          </section>

          <section className="flex flex-col gap-3 rounded-card bg-surface p-9">
            <div className="flex items-center justify-between">
              <span className="text-[20px] font-bold tracking-[-0.02em]">{strategy.name}</span>
              <span className="text-base text-muted">{OPERATING_MODES[mode].label}</span>
            </div>
            <span className="text-lg text-muted">투자 예정 금액 <b className="text-ink">{won(amount)}</b></span>
          </section>

          <section className="flex flex-col gap-3 rounded-card bg-surface p-9">
            <button onClick={toggleAll} className="flex items-center gap-3 pb-2 text-left">
              <Check on={allAgreed} />
              <span className="text-[17px] font-bold">필수 약관 모두 동의</span>
            </button>
            <div className="h-px bg-line" />

            <AgreementRow
              checked={agreed.product}
              onToggle={() => toggleOne('product')}
              label={`${strategy.name} 상품설명서`}
              onView={() => setModal('product')}
            />
            <AgreementRow
              checked={agreed.service}
              onToggle={() => toggleOne('service')}
              label="투자 서비스 필수 약관"
              onView={() => setModal('service')}
            />
            <AgreementRow
              checked={agreed.privacy}
              onToggle={() => toggleOne('privacy')}
              label="개인정보 필수 수집·이용 동의"
              onView={() => setModal('privacy')}
            />

            <div className="flex items-start gap-3 rounded-[14px] bg-[#FFF6EC] px-5 py-4">
              <button onClick={() => toggleOne('riskNotice')} className="mt-0.5 shrink-0">
                <Check on={agreed.riskNotice} />
              </button>
              <p className="text-[15px] leading-[24px] text-[#7A5A1E]">
                투자 결과에 따라 원금의 일부 또는 전부 손실이 발생할 수 있습니다.
              </p>
            </div>
          </section>

          <button
            onClick={onComplete}
            disabled={!allAgreed}
            className="rounded-field py-5 text-[19px] font-bold transition-colors disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
          >
            동의하고 계속하기 →
          </button>
        </div>
      </main>

      {modal === 'product' && (
        <TermsModal title={`${strategy.name} 상품설명서`} body={productBody} onClose={() => setModal(null)} />
      )}
      {modal === 'service' && (
        <TermsModal title="투자 서비스 필수 약관" body={SERVICE_TERMS_BODY} onClose={() => setModal(null)} />
      )}
      {modal === 'privacy' && (
        <TermsModal title="개인정보 필수 수집·이용 동의" body={PRIVACY_TERMS_BODY} onClose={() => setModal(null)} />
      )}
    </div>
  );
}

function AgreementRow({ checked, onToggle, label, onView }: {
  checked: boolean; onToggle: () => void; label: string; onView: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <button onClick={onToggle} className="flex flex-1 items-center gap-3 py-1 text-left">
        <Check on={checked} />
        <span className="text-[16px] leading-[24px] text-[#3F4A43]">{label}</span>
      </button>
      <button onClick={onView} className="shrink-0 text-sm text-subtle underline">
        보기 &gt;
      </button>
    </div>
  );
}

function Check({ on }: { on: boolean }) {
  return (
    <span
      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
        on ? 'bg-lime text-navy' : 'bg-[#F0F2ED] text-white'
      }`}
    >
      ✓
    </span>
  );
}
