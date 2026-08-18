import { useAuthStore } from '../store/authStore';
import type { Screen } from '../types';

interface Props {
  active?: 'strategy' | 'information' | 'portfolio';
  userName: string;
  onNavigate: (s: Screen) => void;
}

/** 전 화면 공통 상단 내비게이션 — "전략 둘러보기"/"나의 포트폴리오"는 로그인 필요 */
const NAV: { key: Props['active']; label: string; to: Screen; guarded: boolean }[] = [
  { key: 'strategy', label: '전략 둘러보기', to: 'strategy', guarded: true },
  { key: 'information', label: '정보', to: 'information', guarded: false },
  // 헤더 라우팅: 나의 포트폴리오 → 05 대시보드
  { key: 'portfolio', label: '나의 포트폴리오', to: 'dashboard', guarded: true },
];

export default function Header({ active, userName, onNavigate }: Props) {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);

  const handleNavClick = (item: (typeof NAV)[number]) => {
    // 로그인이 필요한 메뉴는 인증 여부를 먼저 확인하고, 미로그인 시 로그인/회원가입 화면으로 보낸다
    if (item.guarded && !isLoggedIn) {
      onNavigate('login');
      return;
    }
    onNavigate(item.to);
  };

  return (
    <header className="sticky top-0 z-50 flex h-20 items-center justify-between bg-canvas px-16">
      <div className="flex items-center gap-10">
        <button onClick={() => onNavigate('home')} className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-[7px] bg-navy" />
          <span className="text-[19px] font-bold tracking-[-0.02em]">물림방지</span>
        </button>
        <nav className="flex gap-7">
          {NAV.map((n) => (
            <button
              key={n.key}
              onClick={() => handleNavClick(n)}
              className={`text-base ${active === n.key ? 'font-semibold text-ink' : 'text-muted'}`}
            >
              {n.label}
            </button>
          ))}
        </nav>
      </div>
      <div className="flex items-center gap-2.5 text-[15px] text-muted">
        <span>{userName}님</span>
        <div className="h-[34px] w-[34px] rounded-full bg-[#EAEEE7]" />
      </div>
    </header>
  );
}
