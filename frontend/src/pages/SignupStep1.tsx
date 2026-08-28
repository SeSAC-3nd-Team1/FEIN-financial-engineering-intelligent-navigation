import { useState } from 'react';
import Header from '../components/Header';
import TermsModal from '../components/TermsModal';
import { MIN_SIGNUP_AGE, RE, digitsOnly, meetsMinimumSignupAge } from '../lib/validation';
import type { Agreements, Screen, SignupPersonal } from '../types';

interface Props {
  value: SignupPersonal;
  onChange: (v: SignupPersonal) => void;
  /** 이메일로 인증번호 발송 — 성공하면 App.tsx가 Step 02로 이동시킨다. 실패하면 reject되어 이 화면에 에러를 보여준다. */
  onRequestEmailVerification: (email: string) => Promise<void>;
  userName: string;
  onNavigate: (s: Screen) => void;
}

const TERMS_TEXT: Record<keyof Agreements, { label: string; title: string; body: string }> = {
  b: {
    label: '개인정보 수집·이용 동의',
    title: '개인정보 수집·이용 동의서',
    body: '수집 항목: 이름, 생년월일, 이메일, 휴대폰 번호\n수집·이용 목적: 회원 식별 및 계정 관리, 고객 안내, 서비스 이용 관련 알림, 서비스 운영\n보유 및 이용기간: 회원 탈퇴 시까지\n\n동의를 거부할 권리가 있으나, 필수 동의 사항이므로 거부 시 서비스 이용이 불가합니다.',
  },
  c: {
    label: '서비스 이용약관 동의',
    title: 'FE!N 서비스 이용약관',
    body: '제1조 (목적)\n본 약관은 회사가 제공하는 FE!N 모의투자 서비스의 이용과 관련하여 회사와 회원 간의 권리·의무 및 책임사항을 규정함을 목적으로 합니다.\n\n제2조 (용어의 정의)\n"회원"이란 본 약관에 따라 서비스 이용을 신청하여 승낙을 받은 자를 의미합니다. FE!N은 실제 증권 계좌 개설이나 실제 자금의 매수·매도를 중개하지 않으며, 가상의 자산으로 투자 전략을 체험하는 모의투자 서비스입니다.\n\n제3조 (AI 서비스 이용 안내)\nAI가 제공하는 투자전략 추천, 분석 및 설명은 투자 판단을 돕기 위한 참고 정보이며 특정 금융상품의 매수·매도 또는 투자수익을 보장하지 않습니다. AI가 생성한 정보에는 오류가 포함될 수 있으며, 최종 투자 판단과 결정은 이용자에게 있습니다.',
  },
};

/** 필수 약관 — 모두 true 여야 이메일 인증 진행 가능. AI 기반 맞춤형 서비스 이용 동의는 더 이상
 *  별도 선택 항목으로 받지 않고 회원가입 시 항상 동의로 전송한다(App.tsx 참고). */
const ORDER: (keyof Agreements)[] = ['b', 'c'];

export default function SignupStep1({ value, onChange, onRequestEmailVerification, userName, onNavigate }: Props) {
  const agree = value.agreements;
  const [modal, setModal] = useState<keyof Agreements | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  const allAgreed = ORDER.every((k) => agree[k]);
  const emailValid = RE.email.test(value.email);
  const birthdateComplete = RE.birthdate.test(value.birthdate);
  const isUnderage = birthdateComplete && !meetsMinimumSignupAge(value.birthdate);
  // Step 01 통과 조건: 입력 3개(생년월일은 최소 연령 이상) + 약관 전체 동의(둘 다 필수)
  const canProceed =
    value.name.trim().length > 0 &&
    birthdateComplete &&
    !isUnderage &&
    emailValid &&
    allAgreed;

  const toggleAll = () => {
    const next = !allAgreed;
    onChange({ ...value, agreements: { b: next, c: next } });
  };

  const toggleOne = (k: keyof Agreements) => {
    onChange({ ...value, agreements: { ...agree, [k]: !agree[k] } });
  };

  const handleSubmit = async () => {
    if (!canProceed || sending) return;
    setSending(true);
    setError('');
    try {
      await onRequestEmailVerification(value.email.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : '인증번호를 보내지 못했어요. 잠시 후 다시 시도해주세요.');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header userName={userName} onNavigate={onNavigate} />
      <div className="mx-auto flex w-[520px] flex-col gap-9 py-16">
      <div className="flex flex-col gap-4">
        <span className="text-base font-semibold text-muted">1 / 3</span>
        <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">가입 정보를 입력해주세요.</h1>
        <p className="text-lg leading-[30px] text-muted">FE!N 이용에 필요한 기본 정보를 확인할게요.</p>
      </div>

      <div className="flex flex-col gap-3.5">
        <Field label="이름">
          <input
            value={value.name}
            onChange={(e) => onChange({ ...value, name: e.target.value })}
            placeholder="홍길동"
            className="w-full rounded-field bg-surface px-5 py-4 text-[17px] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
          />
        </Field>
        <Field label="생년월일 6자리">
          <input
            value={value.birthdate}
            inputMode="numeric"
            onChange={(e) => onChange({ ...value, birthdate: digitsOnly(e.target.value, 6) })}
            placeholder="990101"
            className="w-full rounded-field bg-surface px-5 py-4 text-[17px] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
          />
          {isUnderage && (
            <span className="text-sm text-up">만 {MIN_SIGNUP_AGE}세 이상만 가입할 수 있어요.</span>
          )}
        </Field>
        <Field label="이메일">
          <input
            value={value.email}
            type="email"
            onChange={(e) => onChange({ ...value, email: e.target.value })}
            placeholder="name@email.com"
            className="w-full rounded-field bg-surface px-5 py-4 text-[17px] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
          />
          {value.email.length > 0 && !emailValid && (
            <span className="text-sm text-up">올바른 이메일 형식으로 입력해주세요.</span>
          )}
        </Field>
      </div>

      <div className="flex flex-col gap-3 rounded-[20px] bg-surface p-7">
        <button onClick={toggleAll} className="flex items-center gap-3 text-left">
          <Check on={allAgreed} />
          <span className="text-[17px] font-bold">약관 전체 동의</span>
        </button>
        <div className="h-px bg-line" />
        {ORDER.map((k) => (
          <div key={k} className="flex items-center justify-between gap-3">
            <button
              onClick={() => toggleOne(k)}
              className="flex flex-1 items-center gap-3 text-left"
            >
              <Check on={agree[k]} />
              <span className="text-[15px] leading-[24px] text-[#3F4A43]">{TERMS_TEXT[k].label}</span>
            </button>
            {/* 약관 텍스트 클릭 → 상세 모달 */}
            <button onClick={() => setModal(k)} className="shrink-0 text-sm text-subtle underline">
              보기
            </button>
          </div>
        ))}
      </div>

      <button
        onClick={() => void handleSubmit()}
        disabled={!canProceed || sending}
        className="rounded-field py-5 text-[19px] font-bold transition-colors disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
      >
        {sending ? '인증번호 보내는 중...' : '이메일 인증하기'}
      </button>
      {error && <p className="text-sm text-up">{error}</p>}

      {modal && (
        <TermsModal title={TERMS_TEXT[modal].title} body={TERMS_TEXT[modal].body} onClose={() => setModal(null)} />
      )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-[15px] font-semibold text-muted">{label}</span>
      {children}
    </label>
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
