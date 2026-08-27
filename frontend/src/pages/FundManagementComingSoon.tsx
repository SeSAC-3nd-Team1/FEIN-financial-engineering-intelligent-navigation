import { Clock } from 'lucide-react';
import Header from '../components/Header';
import type { Screen } from '../types';

interface Props {
  kind: 'deposit' | 'withdraw';
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
}

const COPY: Record<'deposit' | 'withdraw', { title: string; description: string }> = {
  deposit: {
    title: '추가 투자',
    description:
      '지금 운용 중인 전략에 금액을 더 투자하는 기능이에요. 기존 포지션은 그대로 두고, 추가한 금액만 지금 전략의 목표 비중대로 매수될 예정이에요.',
  },
  withdraw: {
    title: '투자금 출금',
    description:
      '지금 운용 중인 전략에서 투자금 일부 또는 전체를 출금하는 기능이에요. 보유 종목을 비중대로 매도해서 요청한 금액만큼 출금할 예정이에요.',
  },
};

/**
 * 추가 투자 / 투자금 출금 placeholder — Backend/Model contract가 아직 확정되지 않아 실제 금액
 * 입력~실행 Flow는 구현하지 않는다. StrategyComingSoon과 동일한 패턴(Header/back/제목·설명/
 * 단일 "준비 중" 패널/disclaimer)을 그대로 재사용한다 — 가짜 금액/거래/성공 처리를 만들지 않는다.
 * TODO(Backend/Model contract 확정 후): 이 화면을 실제 금액 입력 → 확인 → 실행 → 완료 Flow로 교체한다.
 */
export default function FundManagementComingSoon({ kind, userName, onNavigate, onBack }: Props) {
  const copy = COPY[kind];

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <button
              onClick={onBack}
              className="self-start text-[15px] font-semibold text-muted transition-colors hover:text-navy"
            >
              ← 나의 포트폴리오
            </button>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">{copy.title}</h1>
            <p className="max-w-[820px] text-[19px] leading-8 text-muted">{copy.description}</p>
          </section>

          <section className="flex flex-col items-center gap-5 rounded-card bg-surface px-10 py-20 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-[18px] bg-surface-soft text-muted">
              <Clock size={26} />
            </div>
            <h2 className="text-2xl font-bold tracking-[-0.025em]">{copy.title} 기능을 준비하고 있어요</h2>
            <p className="max-w-[520px] text-[17px] leading-7 text-muted">
              곧 이 화면에서 금액 입력부터 실행까지 진행할 수 있어요.
            </p>
          </section>

          <p className="text-sm leading-[22px] text-subtle">
            ※ 아직 실제 {copy.title} 기능과 연결되지 않았어요. 이 화면은 준비 중 안내입니다.
          </p>
        </div>
      </main>
    </div>
  );
}
