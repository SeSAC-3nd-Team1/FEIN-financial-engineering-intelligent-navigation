import Header from '../components/Header';
import { useAuthStore } from '../store/authStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
}

const HOME_STEPS = [
  { title: '투자성향 알아보기', body: '내 투자 성향을 간단히 알아봐요.' },
  { title: '전략 추천받기', body: '나에게 맞는 투자전략을 찾아드려요.' },
  { title: '이해하고 시작하기', body: '과거 성과와 투자 근거를 확인하고 결정해요.' },
];

/**
 * 00 홈 — 로그인 전 랜딩. "기능/성과를 나열하는 페이지"가 아니라, 물방개와 한 문장으로
 * FE!N이 무엇을 도와주는 서비스인지 바로 알리고 시작 행동(투자성향 진단)으로 보내는 것이 목적이다.
 * 로그인 Home(Navigation Hub)은 Phase 5에서 별도로 구현한다 — 이 컴포넌트는 비로그인 전용.
 */
export default function Home({ userName, onNavigate }: Props) {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);
  // "투자전략"은 로그인이 필요해 미로그인 시 로그인 화면으로 보낸다
  const goStrategy = () => onNavigate(isLoggedIn ? 'strategy-list' : 'login');

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="home" userName={userName} onNavigate={onNavigate} guestCta={{ label: '무료로 시작하기', to: 'login' }} />

      <main className="flex flex-col items-center pb-24">
        <section className="grid w-[1312px] grid-cols-[1fr_auto] items-center gap-16 px-16 pb-24 pt-20">
          <div className="flex flex-col gap-6">
            <h1 className="text-[56px] font-bold leading-[74px] tracking-[-0.04em]">
              투자는 어려워도,<br />내 전략은 이해할 수 있게.
            </h1>
            <p className="max-w-[540px] text-xl leading-[34px] text-muted">
              FE!N이 투자성향을 알아보고<br />나에게 맞는 전략을 쉽게 설명해드려요.
            </p>
            <div className="flex items-center gap-6 pt-3">
              <button onClick={() => onNavigate('login')} className="rounded-field bg-lime px-9 py-5 text-[19px] font-bold text-navy">
                내 투자성향 알아보기 →
              </button>
              <button onClick={goStrategy} className="text-[17px] font-semibold text-muted transition-colors hover:text-navy">
                투자전략 살펴보기 →
              </button>
            </div>
          </div>

          <img src="/character-recommend.png" alt="물방개" className="h-[340px] w-auto object-contain" />
        </section>

        <section className="flex w-[1312px] flex-col gap-10 px-16 pb-24">
          <h2 className="text-4xl font-bold leading-[52px] tracking-[-0.03em]">FE!N에서는 이렇게 시작해요</h2>
          <div className="flex items-start">
            {HOME_STEPS.map((step, i) => (
              <div key={step.title} className="flex items-start">
                <div className="flex w-[300px] flex-col gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#F1FBD4] text-[15px] font-bold text-[#3F5222]">
                    {i + 1}
                  </span>
                  <span className="text-xl font-bold tracking-[-0.02em] text-ink">{step.title}</span>
                  <span className="text-base leading-6 text-muted">{step.body}</span>
                </div>
                {i < HOME_STEPS.length - 1 && <div className="mt-[18px] h-px w-10 shrink-0 bg-line" />}
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
