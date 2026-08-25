import { useAuthStore } from '../store/authStore';
import type { Screen } from '../types';

interface Props { onNavigate: (s: Screen) => void; }

/** 00 홈 — 로그인 전 랜딩. 두 CTA 모두 로그인 화면으로 보낸다 */
export default function Home({ onNavigate }: Props) {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);
  // "투자전략"/"나의 포트폴리오"는 로그인이 필요해 미로그인 시 로그인 화면으로 보낸다
  const goStrategy = () => onNavigate(isLoggedIn ? 'strategy' : 'login');
  // "나의 포트폴리오" → Portfolio.tsx (PDF 1~4p 통합 Power BI 대시보드가 기본 화면)
  const goPortfolio = () => onNavigate(isLoggedIn ? 'portfolio' : 'login');

  return (
    <div className="min-h-screen bg-canvas">
      <header className="sticky top-0 z-50 flex h-20 items-center justify-between bg-canvas px-16">
        <div className="flex items-center gap-10">
          <button onClick={() => onNavigate('home')} className="flex items-center gap-2">
            <img src="/main_logo.png" alt="FE!N" className="h-16 w-auto object-contain" />
          </button>
          <nav className="flex gap-7 text-base text-muted">
            <button onClick={() => onNavigate('home')}>홈</button>
            <button onClick={goStrategy}>투자전략</button>
            <button onClick={() => onNavigate('information')}>인사이트</button>
            <button onClick={goPortfolio}>나의 포트폴리오</button>
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <button onClick={() => onNavigate('login')} className="text-base text-muted">로그인</button>
          <button onClick={() => onNavigate('login')} className="rounded-[10px] bg-lime px-5 py-3 text-base font-bold text-navy">
            무료로 시작하기
          </button>
        </div>
      </header>

      <main className="flex flex-col items-center pb-24">
        <section className="grid w-[1312px] grid-cols-[640px_1fr] items-center gap-16 px-16 pb-24 pt-20">
          <div className="flex flex-col gap-6">
            <span className="self-start rounded-full bg-[#F1FBD4] px-3.5 py-2 text-[15px] font-semibold text-[#3F5222]">
              ✦ 5문항 · 1분이면 끝나요
            </span>
            <h1 className="text-[56px] font-bold leading-[74px] tracking-[-0.04em]">
              어려운 투자전략,<br />직접 해보면 쉬워져요.
            </h1>
            <p className="max-w-[540px] text-xl leading-[34px] text-muted">
              내 투자성향에 맞는 전략을 찾고, 과거 시장에서 내 돈이 어떻게 움직였을지 먼저 체험해보세요.
            </p>
            <div className="flex gap-3 pt-3">
              <button onClick={() => onNavigate('login')} className="rounded-field bg-lime px-9 py-5 text-[19px] font-bold text-navy">
                무료로 시작하기
              </button>
              <button onClick={() => onNavigate('login')} className="rounded-field bg-[#F4F6F1] px-8 py-5 text-[19px] font-semibold text-[#3F4A43]">
                이미 계정이 있어요
              </button>
            </div>
            <p className="text-base text-subtle">전략 체험과 포트폴리오는 로그인 후 이용할 수 있어요</p>
          </div>

          <div className="flex flex-col gap-4 pl-6">
            <Floating label="저변동성 전략" value="나와 92% 잘 맞아요" />
            <Floating label="2020 코로나 폭락" value={'시장보다 15%p\n덜 떨어졌어요'} indent />
            <Floating label="재무 건강검진" value="20개 중 17개 양호" />
          </div>
        </section>

        <section className="flex w-[1312px] flex-col gap-9 px-16 pb-24">
          <h2 className="text-4xl font-bold leading-[52px] tracking-[-0.03em]">1분이면 내 전략을 찾을 수 있어요</h2>
          <div className="grid grid-cols-3 gap-5">
            <Step n="01" title="5문항으로 성향 진단" body="정답은 없어요. 평소 어떻게 할지 고르기만 하면 돼요." />
            <Step n="02" title="과거 시장에서 체험" body="폭락장에 내 돈이 어땠을지 직접 눌러가며 확인해요." />
            <Step n="03" title="10만원부터 시작" body="이해한 다음에 결정해요. 전략은 언제든 바꿀 수 있어요." />
          </div>
        </section>

        <section className="flex w-full flex-col items-center bg-[#F1F3EE] py-24">
          <div className="flex w-[1312px] flex-col gap-10 px-16">
            <div className="flex flex-col gap-4">
              <span className="text-[17px] font-semibold text-[#3F5222]">미리보기</span>
              <h2 className="text-[40px] font-bold leading-[56px] tracking-[-0.035em]">
                시장이 흔들렸던 순간,<br />이 전략은 어땠을까요?
              </h2>
              <p className="max-w-[720px] text-[19px] leading-8 text-muted">
                저변동성 전략에 1,000만원을 넣었다고 가정한 결과예요. 로그인하면 모든 구간을 직접 바꿔가며 볼 수 있어요.
              </p>
            </div>
            <div className="flex items-center justify-between gap-6 rounded-card bg-surface px-12 py-10">
              <div className="flex flex-col gap-2">
                <span className="text-base text-muted">2020 코로나 폭락 · 투자금 1,000만원</span>
                <div className="flex items-baseline gap-3.5">
                  <span className="text-[44px] font-bold tracking-[-0.035em]">830만원</span>
                  <span className="text-[19px] font-semibold text-down">-170만원 (-17.0%)</span>
                </div>
                <span className="text-[17px] text-muted">같은 기간 KOSPI는 -32%였어요</span>
              </div>
              <button onClick={() => onNavigate('login')} className="shrink-0 rounded-field bg-lime px-8 py-[18px] text-lg font-bold text-navy">
                로그인하고 시작하기 →
              </button>
            </div>
          </div>
        </section>

        <section className="mx-16 mt-24 flex w-[1184px] flex-col items-center gap-6 rounded-card bg-navy px-20 py-20">
          <h2 className="text-center text-4xl font-bold leading-[52px] tracking-[-0.03em] text-white">
            1분이면 돼요.<br />내 투자 성향부터 확인해볼까요?
          </h2>
          <p className="text-center text-lg text-[#B9C2BA]">진단은 무료이고, 결과는 전략 추천에만 쓰여요.</p>
          <button onClick={() => onNavigate('login')} className="rounded-field bg-lime px-10 py-5 text-[19px] font-bold text-navy">
            무료로 시작하기
          </button>
        </section>
      </main>
    </div>
  );
}

function Floating({ label, value, indent }: { label: string; value: string; indent?: boolean }) {
  return (
    <div className={`flex flex-col gap-2 rounded-[20px] bg-surface px-8 py-7 shadow-[0_12px_32px_rgba(24,36,58,0.08)] ${indent ? 'ml-14' : ''}`}>
      <span className="text-[15px] text-muted">{label}</span>
      <span className="whitespace-pre-line text-[26px] font-bold leading-[38px] tracking-[-0.025em]">{value}</span>
    </div>
  );
}

function Step({ n, title, body }: { n: string; title: string; body: string }) {
  return (
    <div className="flex flex-col gap-3 rounded-card bg-surface p-10">
      <span className="text-[15px] font-bold text-subtle">{n}</span>
      <span className="text-2xl font-bold tracking-[-0.025em]">{title}</span>
      <span className="text-[17px] leading-7 text-muted">{body}</span>
    </div>
  );
}
