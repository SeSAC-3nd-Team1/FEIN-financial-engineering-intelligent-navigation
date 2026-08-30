import { useRef, useState } from 'react';
import { Info } from 'lucide-react';

interface Props {
  label: string;       // aria-label 문맥, 예: 'CAGR'
  description: string; // 툴팁 본문
}

/**
 * 짧은 용어 설명 아이콘 — hover/click(desktop), tap(mobile), focus(keyboard) 모두에서 열린다.
 * RiskResult.tsx 의 InvestorTypeInfo 를 일반화해 추출한 공용 컴포넌트.
 */
export default function TermTooltip({ label, description }: Props) {
  // hover가 실제로 가능한 입력장치(마우스)에서만 hover로 연다 — 터치는 hover가 없으므로 click(tap)만으로 토글한다.
  const [hoverCapable] = useState(
    () => typeof window !== 'undefined' && window.matchMedia?.('(hover: hover) and (pointer: fine)').matches,
  );
  const [open, setOpen] = useState(false);
  // click/tap은 항상 focus를 함께 일으키는데, focus만으로 열어버리면 클릭 토글과 상태가 꼬인다.
  // pointerdown 시점에 표시해두고, 그 focus는 "포인터가 일으킨 focus"로 판단해 무시한다 —
  // 남는 focus 이벤트(Tab 키 이동)만 진짜 키보드 접근으로 취급한다.
  const pointerActivated = useRef(false);
  const markPointer = () => { pointerActivated.current = true; };

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label={`${label} 설명 보기`}
        aria-expanded={open}
        onMouseDown={markPointer}
        onTouchStart={markPointer}
        onMouseEnter={() => hoverCapable && setOpen(true)}
        onMouseLeave={() => hoverCapable && setOpen(false)}
        onFocus={() => {
          if (pointerActivated.current) { pointerActivated.current = false; return; }
          setOpen(true);
        }}
        onBlur={() => setOpen(false)}
        onClick={() => {
          // 데스크톱은 hover가 이미 열고 mouseleave가 닫아주므로 click은 "열림 보장"만 한다(토글하면 hover 중 클릭 시 바로 닫혀버림).
          // hover가 없는 터치 기기에서는 click(tap)이 유일한 열고 닫는 수단이라 토글로 동작해야 한다.
          if (hoverCapable) { setOpen(true); return; }
          setOpen((o) => !o);
        }}
        className="flex h-6 w-6 items-center justify-center rounded-full text-subtle hover:text-navy"
      >
        <Info size={17} />
      </button>
      {open && (
        <div
          role="tooltip"
          className="absolute left-0 top-full z-10 mt-2 w-[240px] rounded-[14px] bg-navy px-5 py-4 text-[15px] leading-6 text-white shadow-[0_8px_24px_rgba(24,36,58,0.25)]"
        >
          {description}
        </div>
      )}
    </span>
  );
}
