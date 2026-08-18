import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import type { Screen } from '../types';

interface Props {
  onLogin: () => void;
  onSignup: () => void;
  onHome: () => void;
  onNavigate: (s: Screen) => void;
}

/** 로그인 — 기존 회원은 포트폴리오로, "회원가입하기"는 가입 1단계로 */
export default function Login({ onLogin, onSignup, onHome }: Props) {
  const [id, setId] = useState('');
  const [pw, setPw] = useState('');
  const [showPw, setShowPw] = useState(false);
  const canLogin = id.trim().length > 0 && pw.length > 0;

  return (
    <div className="min-h-screen bg-canvas">
      <header className="flex h-20 items-center px-16">
        <button onClick={onHome} className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-[7px] bg-navy" />
          <span className="text-[19px] font-bold tracking-[-0.02em]">물림방지</span>
        </button>
      </header>

      <main className="mx-auto flex w-[440px] flex-col gap-8 py-16">
        <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">다시 오셨네요.</h1>

        <div className="flex flex-col gap-3.5">
          <input
            value={id}
            onChange={(e) => setId(e.target.value)}
            placeholder="아이디"
            className="rounded-field bg-surface px-5 py-4 text-[17px] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
          />
          <div className="relative">
            <input
              type={showPw ? 'text' : 'password'}
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              placeholder="비밀번호"
              onKeyDown={(e) => e.key === 'Enter' && canLogin && onLogin()}
              className="w-full rounded-field bg-surface py-4 pl-5 pr-14 text-[17px] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
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
        </div>

        <button
          onClick={onLogin}
          disabled={!canLogin}
          className="rounded-field py-5 text-[19px] font-bold disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
        >
          로그인
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
