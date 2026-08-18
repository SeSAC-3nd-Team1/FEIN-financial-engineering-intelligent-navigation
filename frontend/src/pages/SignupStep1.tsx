import { useState } from 'react';
import Header from '../components/Header';
import TermsModal from '../components/TermsModal';
import { RE, digitsOnly } from '../lib/validation';
import type { Agreements, Screen, SignupPersonal } from '../types';

interface Props {
  value: SignupPersonal;
  onChange: (v: SignupPersonal) => void;
  onNext: () => void;
  userName: string;
  onNavigate: (s: Screen) => void;
}

const TERMS_TEXT: Record<keyof Agreements, { label: string; title: string; body: string }> = {
  a1: { label: '개인정보 제3자 제공 동의 (KT, LGU+, SKT 알뜰폰)', title: '개인정보 제3자 제공 동의', body: '본인확인을 위해 이름, 생년월일, 휴대폰번호, 통신사 정보를 이동통신사에 제공합니다.\n제공받는 자: KT, LG U+, SK텔레콤(알뜰폰 포함)\n보유 기간: 본인확인 처리 완료 후 즉시 파기' },
  a2: { label: '고유식별정보 처리 동의', title: '고유식별정보 처리 동의', body: '본인확인 기관을 통한 실명 확인을 위해 주민등록번호 등 고유식별정보를 처리합니다.\n처리 목적: 본인확인 및 중복 가입 방지\n보유 기간: 회원 탈퇴 시까지' },
  a3: { label: '통신사 이용약관 동의', title: '통신사 이용약관', body: '이동통신사가 제공하는 본인확인 서비스 이용에 관한 약관입니다.\n서비스 제공자의 귀책이 없는 통신 장애로 인한 인증 실패에 대해서는 책임을 지지 않습니다.' },
  a4: { label: 'KCB 휴대폰 본인확인 서비스 이용약관 동의', title: 'KCB 휴대폰 본인확인 서비스 이용약관', body: '코리아크레딧뷰로(KCB)가 제공하는 휴대폰 본인확인 서비스 이용에 관한 약관입니다.\n본인확인 결과는 서비스 가입 및 본인확인 목적으로만 사용됩니다.' },
  b: { label: '개인정보 수집·이용 동의 (회원가입/휴대폰 본인인증)', title: '개인정보 수집·이용 동의서', body: '수집·이용 목적: 회원가입, 서비스 제공, 본인인증\n수집·이용 항목: 이름, 휴대폰번호, 생년월일, 성별, CI, 통신사\n보유 및 이용기간: 회원 탈퇴 시까지\n\n동의를 거부할 권리가 있으나, 필수 동의 사항이므로 거부 시 서비스 이용이 불가합니다.' },
  c: { label: '준회원 이용약관 동의', title: '준회원 이용약관', body: '제1조 (목적)\n본 약관은 회사가 준회원에게 제공하는 서비스의 이용과 관련하여 회사와 준회원 간의 권리·의무 및 책임사항을 규정함을 목적으로 합니다.\n\n제2조 (용어의 정의)\n"준회원"이란 계좌를 개설하지 않고 본 약관에 따라 서비스 이용을 신청하여 승낙을 받은 자를 의미합니다.' },
};

const ORDER: (keyof Agreements)[] = ['a1', 'a2', 'a3', 'a4', 'b', 'c'];

export default function SignupStep1({ value, onChange, onNext, userName, onNavigate }: Props) {
  const [agree, setAgree] = useState<Agreements>({ a1: false, a2: false, a3: false, a4: false, b: false, c: false });
  const [modal, setModal] = useState<keyof Agreements | null>(null);

  const allAgreed = ORDER.every((k) => agree[k]);
  // Step 01 통과 조건: 입력 3개 + 필수 동의 전체
  const canProceed =
    value.name.trim().length > 0 &&
    RE.birthdate.test(value.birthdate) &&
    RE.phone.test(value.phone) &&
    allAgreed;

  const toggleAll = () => {
    const next = !allAgreed;
    setAgree({ a1: next, a2: next, a3: next, a4: next, b: next, c: next });
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header userName={userName} onNavigate={onNavigate} />
      <div className="mx-auto flex w-[520px] flex-col gap-9 py-16">
      <div className="flex flex-col gap-4">
        <span className="text-base font-semibold text-muted">1 / 3</span>
        <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">본인 정보를 알려주세요.</h1>
        <p className="text-lg leading-[30px] text-muted">휴대폰으로 본인확인을 진행할게요.</p>
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
        </Field>
        <Field label="휴대폰 번호">
          <input
            value={value.phone}
            inputMode="numeric"
            onChange={(e) => onChange({ ...value, phone: digitsOnly(e.target.value, 11) })}
            placeholder="01012345678"
            className="w-full rounded-field bg-surface px-5 py-4 text-[17px] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
          />
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
              onClick={() => setAgree((p) => ({ ...p, [k]: !p[k] }))}
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
        onClick={onNext}
        disabled={!canProceed}
        className="rounded-field py-5 text-[19px] font-bold transition-colors disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
      >
        인증번호 받기
      </button>

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
