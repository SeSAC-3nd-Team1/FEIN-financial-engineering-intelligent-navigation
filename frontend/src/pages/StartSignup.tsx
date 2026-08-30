import { useState } from 'react';
import { RE } from '../lib/validation';
import type { Screen } from '../types';

interface Props {
  onNavigate: (s: Screen) => void;
  /** 입력한 이메일을 SignupPersonal.email에 prefill한 뒤 signup-1로 이동시킨다(App.tsx가 구현) —
   *  새 email verification API/스키마 없이 기존 SignupStep1 인증 Flow를 그대로 이어 쓴다. */
  onContinue: (email: string) => void;
}

/**
 * Home "시작하기" 전용 진입 화면 — Netflix처럼 이메일을 먼저 받고 회원가입을 이어가는 UX.
 * 로그인 폼(아이디/비밀번호)을 먼저 보여주지 않고, 신규 사용자를 곧장 회원가입 방향으로 보낸다.
 * 여기서 하는 일은 이메일 값을 SignupStep1에 넘겨주는 것뿐 — 인증번호 발송/검증은 여전히
 * SignupStep1이 담당한다(기존 Flow 재사용, 새 API 없음).
 */
export default function StartSignup({ onNavigate, onContinue }: Props) {
  const [email, setEmail] = useState('');
  const emailValid = RE.email.test(email);

  const handleContinue = () => {
    if (!emailValid) return;
    onContinue(email.trim());
  };

  return (
    <div className="min-h-screen bg-canvas">
      <header className="flex h-20 items-center px-16">
        <button onClick={() => onNavigate('home')} className="flex items-center gap-2">
          <img src="/main_logo_2.png" alt="FE!N" className="h-16 w-auto object-contain" />
        </button>
      </header>

      <main className="mx-auto flex w-[440px] flex-col gap-8 py-16">
        <div className="flex flex-col gap-3">
          <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">FE!N을 시작해볼까요?</h1>
          <p className="text-lg leading-7 text-muted">투자성향을 확인하고 다양한 투자전략을 살펴보세요.</p>
        </div>

        <div className="flex flex-col gap-3.5">
          <input
            value={email}
            type="email"
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleContinue()}
            placeholder="이메일 주소"
            className="w-full rounded-field bg-surface px-5 py-4 text-[17px] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
          />
          {email.length > 0 && !emailValid && (
            <span className="text-sm text-up">올바른 이메일 형식으로 입력해주세요.</span>
          )}
        </div>

        <button
          onClick={handleContinue}
          disabled={!emailValid}
          className="rounded-field py-5 text-[19px] font-bold disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
        >
          시작하기 →
        </button>

        <div className="flex justify-center gap-2 text-[15px] text-muted">
          <span>이미 가입하셨나요?</span>
          <button onClick={() => onNavigate('login')} className="font-semibold text-ink">로그인</button>
        </div>
      </main>
    </div>
  );
}
