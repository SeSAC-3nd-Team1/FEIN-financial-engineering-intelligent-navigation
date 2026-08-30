import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import Header from '../components/Header';
import { RE, digitsOnly } from '../lib/validation';
import type { Credentials, Screen } from '../types';

interface Props {
  onComplete: (userId: string, password: string, phone: string) => Promise<void>;
  onBack: () => void;
  userName: string;
  onNavigate: (s: Screen) => void;
}

export default function SignupStep3({ onComplete, onBack, userName, onNavigate }: Props) {
  const [v, setV] = useState<Credentials>({ userId: '', password: '', passwordConfirm: '', phone: '' });
  const [showPw, setShowPw] = useState(false);
  const [showPwConfirm, setShowPwConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  const idValid = RE.userId.test(v.userId);
  const pwValid = RE.password.test(v.password);
  const phoneValid = RE.phone.test(v.phone);
  // 불일치는 확인란에 값이 있을 때만 에러로 표시한다
  const mismatch = v.passwordConfirm.length > 0 && v.password !== v.passwordConfirm;

  const canSubmit = idValid && pwValid && !mismatch && v.passwordConfirm.length > 0 && phoneValid;

  const completeSignup = async () => {
    if (!canSubmit || submitting) return;
    setSubmitting(true);
    setSubmitError('');
    try {
      await onComplete(v.userId, v.password, v.phone);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '회원가입을 완료하지 못했습니다.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header userName={userName} onNavigate={onNavigate} />
      <div className="mx-auto flex w-[520px] flex-col gap-9 py-16">
      <div className="flex flex-col gap-4">
        <span className="text-base font-semibold text-muted">3 / 3</span>
        <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">로그인 정보를 만들어주세요.</h1>
      </div>

      <label className="flex flex-col gap-2">
        <span className="text-[15px] font-semibold text-muted">아이디</span>
        <input
          value={v.userId}
          onChange={(e) => setV({ ...v, userId: e.target.value })}
          placeholder="영문·숫자 6~16자"
          className="rounded-field bg-surface px-5 py-4 text-[17px] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
        />
        {v.userId.length > 0 && !idValid && (
          <span className="text-sm text-up">영문과 숫자만 사용해 6~16자로 입력해주세요.</span>
        )}
      </label>

      <PasswordField
        label="비밀번호"
        value={v.password}
        onChange={(t) => setV({ ...v, password: t })}
        show={showPw}
        onToggle={() => setShowPw((s) => !s)}
        placeholder="영문·숫자·특수문자 포함 8자 이상"
        error={v.password.length > 0 && !pwValid ? '영문, 숫자, 특수문자(@$!%*#?&)를 모두 포함해 8자 이상 입력해주세요.' : null}
      />

      <PasswordField
        label="비밀번호 확인"
        value={v.passwordConfirm}
        onChange={(t) => setV({ ...v, passwordConfirm: t })}
        show={showPwConfirm}
        onToggle={() => setShowPwConfirm((s) => !s)}
        placeholder="비밀번호를 한 번 더 입력해주세요"
        error={mismatch ? '비밀번호가 일치하지 않습니다.' : null}
      />

      <label className="flex flex-col gap-2">
        <span className="text-[15px] font-semibold text-muted">휴대폰 번호</span>
        <input
          value={v.phone}
          inputMode="numeric"
          onChange={(e) => setV({ ...v, phone: digitsOnly(e.target.value, 11) })}
          placeholder="01012345678"
          className="rounded-field bg-surface px-5 py-4 text-[17px] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
        />
        {v.phone.length > 0 && !phoneValid && (
          <span className="text-sm text-up">올바른 휴대폰 번호 형식으로 입력해주세요.</span>
        )}
        <span className="text-sm text-muted">고객 안내와 계좌·투자 관련 알림을 위해 사용해요.</span>
        <span className="text-xs text-subtle">개인정보 수집·이용 동의에 따라 저장돼요.</span>
      </label>

      <div className="flex gap-3">
        <button onClick={onBack} className="rounded-field bg-[#F4F6F1] px-7 py-5 text-[17px] font-semibold text-[#3F4A43]">
          이전
        </button>
        <button
          onClick={() => void completeSignup()}
          disabled={!canSubmit || submitting}
          className="flex-1 rounded-field py-5 text-[19px] font-bold disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
        >
          {submitting ? '가입 중...' : '가입하기'}
        </button>
      </div>
      {submitError && <p className="text-sm text-up">{submitError}</p>}
      </div>
    </div>
  );
}

/** 오른쪽 끝 FaEye 토글이 달린 비밀번호 입력 */
function PasswordField({
  label, value, onChange, show, onToggle, placeholder, error,
}: {
  label: string; value: string; onChange: (t: string) => void;
  show: boolean; onToggle: () => void; placeholder: string; error: string | null;
}) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-[15px] font-semibold text-muted">{label}</span>
      <div className="relative">
        <input
          type={show ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={`w-full rounded-field bg-surface py-4 pl-5 pr-14 text-[17px] outline-none ${
            error ? 'shadow-[0_0_0_2px_#E5484D_inset]' : 'shadow-[0_0_0_1px_#E5E9E3_inset] focus:shadow-[0_0_0_2px_#C6F04D_inset]'
          }`}
        />
        <button
          type="button"
          aria-label={show ? '비밀번호 숨기기' : '비밀번호 표시'}
          onClick={onToggle}
          className="absolute right-4 top-1/2 -translate-y-1/2 text-subtle"
        >
          {show ? <EyeOff size={20} /> : <Eye size={20} />}
        </button>
      </div>
      {error && <span className="text-sm text-up">{error}</span>}
    </label>
  );
}
