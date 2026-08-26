import { useEffect, useState } from 'react';
import Header from '../components/Header';
import { useCountdown } from '../hooks/useCountdown';
import { digitsOnly } from '../lib/validation';
import type { Screen } from '../types';

interface Props {
  email: string;
  /** Step 03에서 "이전"으로 돌아왔다가 다시 이 화면에 진입한 경우 true — 이미 인증을 마쳤으므로
   *  코드를 다시 요구하지 않는다(인증 토큰은 1회용이라 재검증 자체가 불가능하기도 하다). */
  verified: boolean;
  expiresInSeconds: number;
  /** 재발송 쿨다운(초) — 서버 rate limit과 맞춰 이 시간 동안은 재발송 버튼을 비활성화한다 */
  resendAfterSeconds: number;
  /** 같은 email로 새 인증번호 재발송 — 실패하면 reject되어 이 화면에 에러를 보여준다 */
  onResend: () => Promise<void>;
  /** 인증번호 확인 — 성공하면 App.tsx가 Step 03로 이동시킨다. 실패하면 reject되어 inline 에러를 보여준다. */
  onVerify: (code: string) => Promise<void>;
  /** verified=true일 때 "다음" — API 호출 없이 곧장 Step 03으로 이동 */
  onContinue: () => void;
  onBack: () => void;
  userName: string;
  onNavigate: (s: Screen) => void;
}

export default function SignupStep2({
  email, verified, expiresInSeconds, resendAfterSeconds, onResend, onVerify, onContinue, onBack, userName, onNavigate,
}: Props) {
  const [otp, setOtp] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState('');
  const timer = useCountdown(expiresInSeconds);
  // 발송 시점마다(최초 진입 포함) 서버 rate limit과 맞춰 재발송 버튼을 잠깐 잠근다 — 이게 없으면
  // 연타로 서버 429(EMAIL_VERIFICATION_COOLDOWN)를 그대로 사용자에게 노출하게 된다.
  const resendCooldown = useCountdown(resendAfterSeconds);

  // 화면 진입과 동시에 타이머 시작 — 이미 인증 완료 상태(재방문)라면 새 타이머가 필요 없다.
  useEffect(() => {
    if (!verified) {
      timer.start();
      resendCooldown.start();
    }
  }, [verified]);

  // 인증번호가 만료됐는데(0:00) 6자리만 채워져 있다고 검증을 시도할 수 있었던 문제 — 만료 여부도 함께 확인한다.
  const expired = timer.remaining <= 0;
  const canVerify = otp.length === 6 && !verifying && !expired;

  const handleVerify = async () => {
    if (!canVerify) return;
    setVerifying(true);
    setError('');
    try {
      await onVerify(otp);
    } catch (e) {
      setError(e instanceof Error ? e.message : '인증번호가 올바르지 않아요.');
    } finally {
      setVerifying(false);
    }
  };

  const handleResend = async () => {
    if (resending || resendCooldown.remaining > 0) return;
    setResending(true);
    setError('');
    try {
      await onResend();
      setOtp('');
      timer.start();
      resendCooldown.start();
    } catch (e) {
      setError(e instanceof Error ? e.message : '인증번호를 다시 보내지 못했어요. 잠시 후 다시 시도해주세요.');
    } finally {
      setResending(false);
    }
  };

  if (verified) {
    return (
      <div className="min-h-screen bg-canvas">
        <Header userName={userName} onNavigate={onNavigate} />
        <div className="mx-auto flex w-[520px] flex-col gap-9 py-16">
          <div className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">2 / 3</span>
            <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">이메일 인증이 완료됐어요.</h1>
            <p className="text-lg leading-[30px] text-muted">{email} 인증을 이미 완료했어요.</p>
          </div>
          <div className="flex gap-3">
            <button onClick={onBack} className="rounded-field bg-[#F4F6F1] px-7 py-5 text-[17px] font-semibold text-[#3F4A43]">
              이전
            </button>
            <button onClick={onContinue} className="flex-1 rounded-field bg-lime py-5 text-[19px] font-bold text-navy">
              다음
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-canvas">
      <Header userName={userName} onNavigate={onNavigate} />
      <div className="mx-auto flex w-[520px] flex-col gap-9 py-16">
      <div className="flex flex-col gap-4">
        <span className="text-base font-semibold text-muted">2 / 3</span>
        <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">이메일 인증번호를 입력해주세요.</h1>
        <p className="text-lg leading-[30px] text-muted">{email}으로 6자리 인증번호를 보냈어요.</p>
      </div>

      <div className="flex items-center gap-3">
        <input
          value={otp}
          inputMode="numeric"
          onChange={(e) => { setOtp(digitsOnly(e.target.value, 6)); setError(''); }}
          placeholder="000000"
          className="flex-1 rounded-field bg-surface px-5 py-4 text-[22px] tracking-[0.3em] shadow-[0_0_0_1px_#E5E9E3_inset] outline-none focus:shadow-[0_0_0_2px_#C6F04D_inset]"
        />
        {/* 입력창 옆 남은 시간 카운트다운 */}
        <span className="w-16 text-right text-[17px] font-bold text-down">{timer.label}</span>
      </div>
      {expired && !error && <p className="text-sm text-up">인증번호가 만료됐어요. 다시 받아주세요.</p>}
      {error && <p className="text-sm text-up">{error}</p>}

      <button
        onClick={() => void handleResend()}
        disabled={resending || resendCooldown.remaining > 0}
        className="self-start text-[15px] text-subtle underline disabled:cursor-default disabled:no-underline disabled:text-[#A6AFA7]"
      >
        {resendCooldown.remaining > 0 ? `인증번호 다시 받기 (${resendCooldown.label})` : '인증번호 다시 받기'}
      </button>

      <div className="flex gap-3">
        <button onClick={onBack} className="rounded-field bg-[#F4F6F1] px-7 py-5 text-[17px] font-semibold text-[#3F4A43]">
          이전
        </button>
        <button
          onClick={() => void handleVerify()}
          disabled={!canVerify}
          className="flex-1 rounded-field py-5 text-[19px] font-bold disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
        >
          {verifying ? '확인하는 중...' : '인증 완료'}
        </button>
      </div>
      </div>
    </div>
  );
}
