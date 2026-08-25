import { useAuthStore } from '../store/authStore';
import type { Screen } from '../types';

interface Props {
  active?: 'home' | 'strategy' | 'information' | 'portfolio';
  userName: string;
  onNavigate: (s: Screen) => void;
}

/**
 * 전 화면 공통 상단 내비게이션 — "투자전략"/"나의 포트폴리오"는 로그인 필요.
 * "인사이트"는 기존 "정보" 화면(route: information)의 라벨만 바꾼 것 — 화면/route/내부 UI는 그대로다.
 * "투자전략"의 목적지는 전략 목록(strategy-list) — key는 상세(strategy) 화면과 동일하게 'strategy'를
 * 써서, Strategy Detail에서도 이 메뉴가 계속 active로 표시되게 한다(StrategyList/StrategyDetail 모두
 * Header에 active="strategy"를 전달).
 */
const NAV: { key: Props['active']; label: string; to: Screen; guarded: boolean }[] = [
  { key: 'home', label: '홈', to: 'home', guarded: false },
  { key: 'strategy', label: '투자전략', to: 'strategy-list', guarded: true },
  { key: 'information', label: '인사이트', to: 'information', guarded: false },
  // 헤더 라우팅: 나의 포트폴리오 → Portfolio.tsx (PDF 1~4p 통합 Power BI 대시보드가 기본 화면)
  { key: 'portfolio', label: '나의 포트폴리오', to: 'portfolio', guarded: true },
];

export default function Header({ active, userName, onNavigate }: Props) {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);
  const logout = useAuthStore((s) => s.logout);

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
          <img src="/main_logo.png" alt="FE!N" className="h-16 w-auto object-contain" />
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
      {/* 비로그인 상태(예: 회원가입 진행 중, "정보" 공개 화면)에서는 사용자명을 노출하지 않는다 */}
      {isLoggedIn ? (
        <div className="flex items-center gap-2.5 text-[15px] text-muted">
          <span>{userName}님</span>
          <div className="h-[34px] w-[34px] rounded-full bg-[#EAEEE7]" />
          <button onClick={() => { void logout(); onNavigate('home'); }} className="ml-2 text-sm underline">로그아웃</button>
        </div>
      ) : (
        <button onClick={() => onNavigate('login')} className="text-[15px] font-semibold text-ink">
          로그인
        </button>
      )}
    </header>
  );
}
