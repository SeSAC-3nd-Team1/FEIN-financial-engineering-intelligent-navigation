import { useEffect, useState } from 'react';
import Header from '../components/Header';
import { useCountdown } from '../hooks/useCountdown';
import { digitsOnly } from '../lib/validation';
import type { Screen } from '../types';

interface Props {
  phone: string;
  onNext: () => void;
  onBack: () => void;
  userName: string;
  onNavigate: (s: Screen) => void;
}

export default function SignupStep2({ phone, onNext, onBack, userName, onNavigate }: Props) {
  const [otp, setOtp] = useState('');
  const timer = useCountdown(300); // 5:00

  // 화면 진입과 동시에 타이머 시작
  useEffect(() => { timer.start(); }, []);

  // TEST MODE: 6자리가 채워지면 서버 확인 없이 즉시 버튼 활성화
  const canProceed = otp.length === 6;

  return (
    <div className="min-h-screen bg-canvas">
      <Header userName={userName} onNavigate={onNavigate} />
      <div className="mx-auto flex w-[520px] flex-col gap-9 py-16">
      <div className="flex flex-col gap-4">
        <span className="text-base font-semibold text-muted">2 / 3</span>
        <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">인증번호를 입력해주세요.</h1>
        <p className="text-lg leading-[30px] text-muted">{phone}로 6자리 숫자를 보냈어요.</p>
      </div>

      <div className="flex items-center gap-3">
        <input
          value={otp}
          inputMode="numeric"
          onChange={(e) => setOtp(digitsOnly(e.target.value, 6))}
          placeholder="000000"
          className="flex-1 rounded-field bg-surface px-5 py-4 text-[22px] tracking-[0.3em] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
        />
        {/* 입력창 옆 5분 카운트다운 */}
        <span className="w-16 text-right text-[17px] font-bold text-down">{timer.label}</span>
      </div>

      <button onClick={() => timer.start()} className="self-start text-[15px] text-subtle underline">
        인증번호 다시 받기
      </button>

      <div className="flex gap-3">
        <button onClick={onBack} className="rounded-field bg-[#F4F6F1] px-7 py-5 text-[17px] font-semibold text-[#3F4A43]">
          이전
        </button>
        <button
          onClick={onNext}
          disabled={!canProceed}
          className="flex-1 rounded-field py-5 text-[19px] font-bold disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
        >
          인증 완료
        </button>
      </div>
      </div>
    </div>
  );
}
