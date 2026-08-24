import { useState } from 'react';
import Header from '../components/Header';
import TermsModal from '../components/TermsModal';
import { digitsOnly } from '../lib/validation';
import type { SesacAccount } from '../store/investmentStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  strategyName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
  /** 계좌 연결 완료 — App.tsx가 investmentStore에 반영하고 다음 단계로 라우팅한다 */
  onComplete: (account: SesacAccount) => void;
}

type Phase = 'choice' | 'link-select' | 'link-auth' | 'open-terms' | 'open-auth' | 'done';

/** MOCK — 실제 SeSAC증권 API 연동 전까지, "조회되는 기존 계좌"는 데모용 고정값 하나만 제공한다 */
const MOCK_EXISTING_ACCOUNT: SesacAccount = { accountNumber: '123-****-5678', balance: 0 };
const MOCK_NEW_ACCOUNT: SesacAccount = { accountNumber: '045-****-9081', balance: 0 };

const ACCOUNT_OPEN_TERMS_BODY =
  '제1조 (목적)\n본 약관은 SeSAC증권 계좌개설 및 FE!N 서비스 연계 이용에 관한 사항을 규정합니다.\n\n제2조 (계좌 이용)\n개설된 계좌는 FE!N에서 선택한 투자 전략에 따른 매매 실행 및 자산 관리 목적으로 이용됩니다.\n\n제3조 (수수료 및 비용)\n계좌 운용에 따른 이용 수수료 및 거래비용은 FE!N 투자 서비스 약관에 따릅니다.';

export default function InvestAccount({ userName, strategyName, onNavigate, onBack, onComplete }: Props) {
  const [phase, setPhase] = useState<Phase>('choice');
  const [linkedAccount, setLinkedAccount] = useState<SesacAccount | null>(null);
  const [openTermsAgreed, setOpenTermsAgreed] = useState(false);
  const [showOpenTerms, setShowOpenTerms] = useState(false);

  const back = () => {
    if (phase === 'choice') { onBack(); return; }
    if (phase === 'link-select' || phase === 'open-terms') { setPhase('choice'); return; }
    if (phase === 'link-auth') { setPhase('link-select'); return; }
    if (phase === 'open-auth') { setPhase('open-terms'); return; }
    setPhase('choice');
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[720px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <button onClick={back} className="self-start text-base font-semibold text-muted">← 이전으로</button>
            <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">투자할 계좌를 준비해주세요</h1>
            <p className="text-lg leading-[30px] text-muted">
              FE!N에서 {strategyName}으로 실제 투자를 시작하려면<br />SeSAC증권 계좌 연결이 필요해요.
            </p>
          </section>

          {phase === 'choice' && (
            <div className="grid grid-cols-2 gap-5">
              <ChoiceCard
                title="이미 SeSAC증권 계좌가 있어요"
                desc="사용 중인 계좌를 FE!N과 연결해서 바로 사용할 수 있어요."
                cta="기존 계좌 연동하기 →"
                onClick={() => setPhase('link-select')}
              />
              <ChoiceCard
                title="SeSAC증권 계좌가 없어요"
                desc="새로운 SeSAC증권 계좌를 개설하고 투자를 시작할 수 있어요."
                cta="새 계좌 만들기 →"
                onClick={() => setPhase('open-terms')}
              />
            </div>
          )}

          {phase === 'link-select' && (
            <StepCard title="SeSAC증권 계좌 확인" desc="FE!N과 연결할 계좌를 선택해주세요.">
              <button
                onClick={() => { setLinkedAccount(MOCK_EXISTING_ACCOUNT); setPhase('link-auth'); }}
                className="flex items-center justify-between rounded-[16px] bg-canvas px-7 py-6 text-left shadow-[0_0_0_1px_#E5E9E3_inset]"
              >
                <div className="flex flex-col gap-1">
                  <span className="text-[17px] font-bold text-ink">SeSAC증권 종합계좌</span>
                  <span className="text-base text-muted">{MOCK_EXISTING_ACCOUNT.accountNumber}</span>
                </div>
                <span className="text-base font-semibold text-navy">선택 →</span>
              </button>
            </StepCard>
          )}

          {phase === 'link-auth' && linkedAccount && (
            <MockOtpStep
              title="본인인증"
              desc={`${linkedAccount.accountNumber} 계좌 연결을 위해 인증번호를 입력해주세요.`}
              onVerified={() => setPhase('done')}
            />
          )}

          {phase === 'open-terms' && (
            <StepCard title="SeSAC증권 계좌개설" desc="계좌개설을 위한 약관에 동의해주세요.">
              <button
                onClick={() => setOpenTermsAgreed((v) => !v)}
                className="flex items-center gap-3 rounded-[16px] bg-canvas px-7 py-6 text-left shadow-[0_0_0_1px_#E5E9E3_inset]"
              >
                <Check on={openTermsAgreed} />
                <span className="flex-1 text-[16px] leading-[24px] text-[#3F4A43]">SeSAC증권 계좌개설 약관에 동의합니다</span>
                <span
                  onClick={(e) => { e.stopPropagation(); setShowOpenTerms(true); }}
                  className="shrink-0 text-sm text-subtle underline"
                >
                  보기 &gt;
                </span>
              </button>
              <button
                onClick={() => setPhase('open-auth')}
                disabled={!openTermsAgreed}
                className="rounded-field py-5 text-[19px] font-bold transition-colors disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
              >
                동의하고 계속하기 →
              </button>
            </StepCard>
          )}

          {phase === 'open-auth' && (
            <MockOtpStep
              title="본인인증"
              desc="새 SeSAC증권 계좌 개설을 위해 인증번호를 입력해주세요."
              onVerified={() => { setLinkedAccount(MOCK_NEW_ACCOUNT); setPhase('done'); }}
            />
          )}

          {phase === 'done' && linkedAccount && (
            <section className="flex flex-col items-center gap-8 rounded-card bg-surface px-11 py-16 text-center">
              <div className="flex h-[72px] w-[72px] items-center justify-center rounded-[22px] bg-lime text-[32px] text-navy">✓</div>
              <div className="flex flex-col gap-2">
                <h2 className="text-[28px] font-bold tracking-[-0.03em]">FE!N 연결이 완료됐어요</h2>
                <p className="text-lg text-muted">SeSAC증권 종합계좌 {linkedAccount.accountNumber}</p>
              </div>
              <button
                onClick={() => onComplete(linkedAccount)}
                className="rounded-field bg-lime px-10 py-5 text-[19px] font-bold text-navy"
              >
                다음 →
              </button>
            </section>
          )}
        </div>
      </main>

      {showOpenTerms && (
        <TermsModal title="SeSAC증권 계좌개설 약관" body={ACCOUNT_OPEN_TERMS_BODY} onClose={() => setShowOpenTerms(false)} />
      )}
    </div>
  );
}

function ChoiceCard({ title, desc, cta, onClick }: { title: string; desc: string; cta: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col gap-6 rounded-card bg-surface p-9 text-left shadow-[0_0_0_1px_#E5E9E3_inset] hover:shadow-[0_0_0_2px_#C6F04D_inset]"
    >
      <div className="flex flex-col gap-2">
        <span className="text-[20px] font-bold tracking-[-0.02em]">{title}</span>
        <span className="text-[15px] leading-[24px] text-muted">{desc}</span>
      </div>
      <span className="self-start text-base font-bold text-navy">{cta}</span>
    </button>
  );
}

function StepCard({ title, desc, children }: { title: string; desc: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-6 rounded-card bg-surface p-9">
      <div className="flex flex-col gap-2">
        <h2 className="text-[22px] font-bold tracking-[-0.025em]">{title}</h2>
        <p className="text-base text-muted">{desc}</p>
      </div>
      {children}
    </section>
  );
}

/** PoC 본인인증 Mock — 실제 인증 대신 6자리 숫자만 채우면 통과한다 (SignupStep2 OTP 패턴과 동일) */
function MockOtpStep({ title, desc, onVerified }: { title: string; desc: string; onVerified: () => void }) {
  const [otp, setOtp] = useState('');
  return (
    <StepCard title={title} desc={desc}>
      <input
        value={otp}
        inputMode="numeric"
        onChange={(e) => setOtp(digitsOnly(e.target.value, 6))}
        placeholder="000000"
        className="rounded-field bg-canvas px-5 py-4 text-[22px] tracking-[0.3em] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
      />
      <button
        onClick={onVerified}
        disabled={otp.length !== 6}
        className="rounded-field py-5 text-[19px] font-bold transition-colors disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
      >
        인증 완료
      </button>
    </StepCard>
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
