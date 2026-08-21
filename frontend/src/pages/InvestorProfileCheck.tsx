import Header from '../components/Header';
import { answerLabel } from '../lib/investorProfile';
import { useAuthStore } from '../store/authStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  /** "현재 정보로 계속하기" — 원래 하려던 실제 투자 시작 플로우로 이어간다 */
  onContinue: () => void;
  /** "정보가 달라졌어요" — 투자자 정보 확인(7문항)을 다시 진행한다 */
  onRediagnose: () => void;
}

const formatDate = (iso: string) => {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}`;
};

/** 이미 투자자 정보 확인을 완료한 사용자가 실제 투자를 시작할 때 보는 확인 화면 — 같은 7문항을 반복하지 않는다 */
export default function InvestorProfileCheck({ userName, onNavigate, onContinue, onRediagnose }: Props) {
  const investorType = useAuthStore((s) => s.investorType);
  const completedAt = useAuthStore((s) => s.investorProfileCompletedAt);
  const answers = useAuthStore((s) => s.investorAnswers);

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[640px] flex-col gap-10">
          <div className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">실제 투자 시작 전 확인</span>
            <h1 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">투자자 정보를 확인해주세요.</h1>
            <p className="text-lg leading-[30px] text-muted">
              최근 확인한 투자자 정보로 계속 진행할지, 다시 확인할지 선택해주세요.
            </p>
          </div>

          <div className="flex flex-col gap-6 rounded-card bg-surface px-11 py-9">
            <div className="flex items-center justify-between">
              <span className="text-[15px] text-muted">최근 확인한 투자성향</span>
              <span className="rounded-full bg-lime px-4 py-2 text-sm font-bold text-navy">{investorType ?? '-'}</span>
            </div>
            <div className="h-px bg-line" />
            <Row label="확인일" value={completedAt ? formatDate(completedAt) : '-'} />
            <Row label="투자 목적" value={answerLabel(3, answers?.[3])} />
            <Row label="투자 경험" value={answerLabel(0, answers?.[0])} />
          </div>

          <div className="flex flex-col gap-3">
            <button onClick={onContinue} className="rounded-field bg-lime py-5 text-[19px] font-bold text-navy">
              현재 정보로 계속하기
            </button>
            <button onClick={onRediagnose} className="rounded-field bg-[#F4F6F1] py-5 text-[17px] font-semibold text-[#3F4A43]">
              정보가 달라졌어요
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[15px] text-muted">{label}</span>
      <span className="text-[17px] font-semibold text-ink">{value}</span>
    </div>
  );
}
