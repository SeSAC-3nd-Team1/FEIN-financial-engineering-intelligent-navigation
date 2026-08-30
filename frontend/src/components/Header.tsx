import { useState } from 'react';
import { Menu, X } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import type { Screen } from '../types';

interface Props {
  active?: 'home' | 'strategy' | 'information' | 'portfolio';
  userName: string;
  onNavigate: (s: Screen) => void;
  /** 비로그인 상태일 때 "로그인" 옆에 추가로 보여줄 CTA — 현재 비로그인 Home에서만 사용.
   * onClick으로 받는 이유: Home의 CTA는 로그인 화면 진입 context("home")를 함께 기록해야 해서
   * 단순 화면 이동(Screen) 이상의 동작이 필요하다. */
  guestCta?: { label: string; onClick: () => void };
}

/**
 * 전 화면 공통 상단 내비게이션 — "나의 포트폴리오"만 로그인 필요(개인 투자 데이터 영역).
 * "홈"/"투자전략"/"인사이트"는 비회원도 공개(PUBLIC) — 전략을 이해·탐색하는 것과, 그 전략으로
 * 직접 투자를 실행하는 것은 다른 권한이라는 정책에 따른 것 (StrategyDetail의 "이 전략으로
 * 시작하기"·백테스트 기간 변경 등 "조작" 행동만 그 화면 내부에서 개별적으로 로그인을 요구한다).
 * "인사이트"는 기존 "정보" 화면(route: information)의 라벨만 바꾼 것 — 화면/route/내부 UI는 그대로다.
 * "투자전략"의 목적지는 전략 목록(strategy-list) — key는 상세(strategy) 화면과 동일하게 'strategy'를
 * 써서, Strategy Detail에서도 이 메뉴가 계속 active로 표시되게 한다(StrategyList/StrategyDetail 모두
 * Header에 active="strategy"를 전달).
 *
 * md(768px) 미만에서는 인라인 nav/우측 유저 정보 대신 햄버거 버튼 + 드롭다운 메뉴로 전환한다 —
 * 고정 flex 행에 5개 라벨을 그대로 욱여넣으면 좁은 화면에서 한글이 한 글자씩 줄바꿈된다.
 */
const NAV: { key: Props['active']; label: string; to: Screen; guarded: boolean }[] = [
  { key: 'home', label: '홈', to: 'home', guarded: false },
  { key: 'strategy', label: '투자전략', to: 'strategy-list', guarded: false },
  { key: 'information', label: '인사이트', to: 'information', guarded: false },
  // 헤더 라우팅: 나의 포트폴리오 → Portfolio.tsx (PDF 1~4p 통합 Power BI 대시보드가 기본 화면)
  { key: 'portfolio', label: '나의 포트폴리오', to: 'portfolio', guarded: true },
];

export default function Header({ active, userName, onNavigate, guestCta }: Props) {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);
  const logout = useAuthStore((s) => s.logout);
  const [menuOpen, setMenuOpen] = useState(false);

  const handleNavClick = (item: (typeof NAV)[number]) => {
    setMenuOpen(false);
    // 로그인이 필요한 메뉴는 인증 여부를 먼저 확인하고, 미로그인 시 로그인/회원가입 화면으로 보낸다
    if (item.guarded && !isLoggedIn) {
      onNavigate('login');
      return;
    }
    onNavigate(item.to);
  };

  return (
    <header className="sticky top-0 z-50 flex h-20 items-center justify-between gap-4 bg-canvas px-5 sm:px-8 md:px-16">
      <div className="flex items-center gap-10">
        <button onClick={() => { setMenuOpen(false); onNavigate('home'); }} className="flex shrink-0 items-center gap-2">
          <img src="/main_logo_2.png" alt="FE!N" className="h-12 w-auto object-contain md:h-16" />
        </button>
        <nav className="hidden gap-7 md:flex">
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

      {/* 데스크톱 우측 영역 — md 미만에서는 햄버거 메뉴 안으로 옮겨간다 */}
      <div className="hidden items-center md:flex">
        {/* 비로그인 상태(예: 회원가입 진행 중, "정보" 공개 화면)에서는 사용자명을 노출하지 않는다 */}
        {isLoggedIn ? (
          <div className="flex items-center gap-2.5 text-[15px] text-muted">
            <span>{userName}님</span>
            <div className="h-[34px] w-[34px] rounded-full bg-[#EAEEE7]" />
            <button onClick={() => { void logout(); onNavigate('home'); }} className="ml-2 text-sm underline">로그아웃</button>
          </div>
        ) : (
          <div className="flex items-center gap-4">
            <button onClick={() => onNavigate('login')} className="text-[15px] font-semibold text-ink">
              로그인
            </button>
            {guestCta && (
              <button
                onClick={guestCta.onClick}
                className="rounded-[10px] bg-lime px-5 py-3 text-base font-bold text-navy"
              >
                {guestCta.label}
              </button>
            )}
          </div>
        )}
      </div>

      <button
        onClick={() => setMenuOpen((o) => !o)}
        aria-label={menuOpen ? '메뉴 닫기' : '메뉴 열기'}
        aria-expanded={menuOpen}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-ink md:hidden"
      >
        {menuOpen ? <X size={24} /> : <Menu size={24} />}
      </button>

      {menuOpen && (
        <div className="absolute left-0 right-0 top-20 z-50 flex flex-col gap-1 border-t border-line bg-surface p-5 shadow-[0_12px_28px_rgba(24,36,58,0.12)] md:hidden">
          {NAV.map((n) => (
            <button
              key={n.key}
              onClick={() => handleNavClick(n)}
              className={`rounded-field px-4 py-3 text-left text-base ${
                active === n.key ? 'bg-canvas font-semibold text-ink' : 'text-muted'
              }`}
            >
              {n.label}
            </button>
          ))}
          <div className="mt-2 flex flex-col gap-3 border-t border-line px-4 pt-4">
            {isLoggedIn ? (
              <div className="flex items-center justify-between">
                <span className="text-[15px] text-muted">{userName}님</span>
                <button
                  onClick={() => { setMenuOpen(false); void logout(); onNavigate('home'); }}
                  className="text-sm font-semibold text-ink underline"
                >
                  로그아웃
                </button>
              </div>
            ) : (
              <>
                <button
                  onClick={() => { setMenuOpen(false); onNavigate('login'); }}
                  className="self-start text-[15px] font-semibold text-ink"
                >
                  로그인
                </button>
                {guestCta && (
                  <button
                    onClick={() => { setMenuOpen(false); guestCta.onClick(); }}
                    className="rounded-[10px] bg-lime px-5 py-3 text-base font-bold text-navy"
                  >
                    {guestCta.label}
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
