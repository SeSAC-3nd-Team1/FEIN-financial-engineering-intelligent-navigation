import { useState } from 'react';
import type { ReactNode } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import type { Screen } from '../types';

export type LoginContext = 'header' | 'home' | 'strategy';

interface Props {
  onLogin: () => void;
  onSignup: () => void;
  onHome: () => void;
  onNavigate: (s: Screen) => void;
  /** 로그인 화면에 진입한 경로 — title/subtitle만 바뀌고 폼/버튼/레이아웃은 동일하다 */
  context: LoginContext;
}

const LOGIN_COPY: Record<LoginContext, { title: ReactNode; subtitle: string }> = {
  header: { title: '다시 오셨네요.', subtitle: '로그인하고 FE!N을 계속 이용해보세요.' },
  home: { title: 'FE!N을 시작해볼까요?', subtitle: '로그인하거나 회원가입하고 내 투자성향을 알아보세요.' },
  // 440px 고정폭에서 줄바꿈 없이 두면 "…시작해볼까 / 요?"처럼 어색하게 끊겨 자연스러운 어절 경계에서
  // 줄을 바꾼다 — 문구/폭/font-size는 그대로다.
  strategy: { title: <>이 전략으로<br />시작해볼까요?</>, subtitle: '로그인하거나 회원가입하고 투자 준비를 이어가세요.' },
};

/** 로그인 — 기존 회원은 포트폴리오로, "회원가입하기"는 가입 1단계로 */
export default function Login({ onLogin, onSignup, onHome, context }: Props) {
  const { title, subtitle } = LOGIN_COPY[context];
  const login = useAuthStore((s) => s.login);
  const [id, setId] = useState('');
  const [pw, setPw] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [invalid, setInvalid] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const canLogin = id.trim().length > 0 && pw.length > 0;

  const handleLogin = async () => {
    if (!canLogin || submitting) return;
    setSubmitting(true);
    setErrorMessage('');
    try {
      await login(id.trim(), pw);
      setInvalid(false);
      onLogin();
    } catch (error) {
      setInvalid(true);
      setErrorMessage(error instanceof Error ? error.message : '로그인 요청을 처리하지 못했습니다.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas">
      <header className="flex h-20 items-center px-16">
        <button onClick={onHome} className="flex items-center gap-2">
          <img src="/main_logo_2.png" alt="FE!N" className="h-16 w-auto object-contain" />
        </button>
      </header>

      <main className="mx-auto flex w-[440px] flex-col gap-8 py-16">
        <div className="flex flex-col gap-3">
          <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">{title}</h1>
          <p className="text-lg leading-7 text-muted">{subtitle}</p>
        </div>

        <div className="flex flex-col gap-3.5">
          <input
            value={id}
            onChange={(e) => { setId(e.target.value); setInvalid(false); setErrorMessage(''); }}
            placeholder="아이디"
            className={`rounded-field bg-surface px-5 py-4 text-[17px] outline-none ${
              invalid ? 'shadow-[0_0_0_2px_#E5484D_inset]' : 'shadow-[0_0_0_1px_#E5E9E3_inset] focus:shadow-[0_0_0_2px_#C6F04D_inset]'
            }`}
          />
          <div className="relative">
            <input
              type={showPw ? 'text' : 'password'}
              value={pw}
              onChange={(e) => { setPw(e.target.value); setInvalid(false); setErrorMessage(''); }}
              placeholder="비밀번호"
              onKeyDown={(e) => e.key === 'Enter' && void handleLogin()}
              className={`w-full rounded-field bg-surface py-4 pl-5 pr-14 text-[17px] outline-none ${
                invalid ? 'shadow-[0_0_0_2px_#E5484D_inset]' : 'shadow-[0_0_0_1px_#E5E9E3_inset] focus:shadow-[0_0_0_2px_#C6F04D_inset]'
              }`}
            />
            <button
              type="button"
              aria-label={showPw ? '비밀번호 숨기기' : '비밀번호 표시'}
              onClick={() => setShowPw((s) => !s)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-subtle"
            >
              {showPw ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>
          {invalid && (
            <span className="text-sm text-up">
              {errorMessage || '아이디 또는 비밀번호가 올바르지 않습니다. 입력한 정보를 다시 확인해 주세요.'}
            </span>
          )}
        </div>

        <button
          onClick={() => void handleLogin()}
          disabled={!canLogin || submitting}
          className="rounded-field py-5 text-[19px] font-bold disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
        >
          {submitting ? '로그인 중...' : '로그인'}
        </button>

        <div className="flex justify-center gap-5 text-[15px] text-muted">
          <span>아이디 찾기</span>
          <span className="text-line">|</span>
          <span>비밀번호 찾기</span>
          <span className="text-line">|</span>
          <button onClick={onSignup} className="font-semibold text-ink">회원가입하기</button>
        </div>
      </main>
    </div>
  );
}
