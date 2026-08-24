const STEPS = ['전략 선택', '계좌 준비', '입금', '투자 시작'] as const;

/** 투자 시작 Flow(입금/최종확인 화면 공용) 진행 상태 — 전략 선택·계좌 준비는 이 두 화면에 도달한 시점엔 항상 완료 상태다 */
export default function InvestmentProgress({ current }: { current: 'deposit' | 'confirm' }) {
  const currentIndex = current === 'deposit' ? 2 : 3;

  return (
    <div className="flex items-center">
      {STEPS.map((label, i) => (
        <div key={label} className="flex items-center">
          <div className="flex flex-col items-center gap-2">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                i < currentIndex ? 'bg-lime text-navy' : i === currentIndex ? 'bg-navy text-white' : 'bg-[#F0F2ED] text-white'
              }`}
            >
              {i < currentIndex ? '✓' : i === currentIndex ? '●' : '○'}
            </span>
            <span className={`text-[13px] ${i <= currentIndex ? 'font-semibold text-ink' : 'text-subtle'}`}>{label}</span>
          </div>
          {i < STEPS.length - 1 && <div className="mx-3 h-px w-10 bg-line" />}
        </div>
      ))}
    </div>
  );
}
