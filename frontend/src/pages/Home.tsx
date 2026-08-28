import CarGoalProgress from '../components/CarGoalProgress';
import Header from '../components/Header';
import { useAuthStore } from '../store/authStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (s: Screen) => void;
  /** "내 투자성향 알아보기"/"무료로 시작하기" — 로그인 화면에 context="home"으로 진입시킨다 */
  onRequestLogin: () => void;
}

const HOME_STEPS = [
  { title: '투자성향 알아보기', body: '내 투자 성향을 간단히 알아봐요.' },
  { title: '전략 추천받기', body: '나에게 맞는 투자전략을 찾아드려요.' },
  { title: '이해하고 시작하기', body: '과거 성과와 투자 근거를 확인하고 결정해요.' },
];

/**
 * 00 홈 — 같은 route를 로그인 여부로 분기해서 쓴다.
 * 비로그인: 브랜드 랜딩(Phase 4). 로그인: Header "홈"을 직접 눌렀을 때만 보이는 Personal
 * Navigation Hub(Phase 5) — Portfolio와 역할이 겹치지 않도록 투자 데이터는 전혀 보여주지 않는다.
 * 로그인 직후 자동 랜딩 규칙(Portfolio/입금 요청)은 App.tsx의 navigate()가 그대로 담당하고 있어
 * 여기서는 건드리지 않는다.
 */
export default function Home({ userName, onNavigate, onRequestLogin }: Props) {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="home" userName={userName} onNavigate={onNavigate} guestCta={{ label: '무료로 시작하기', onClick: onRequestLogin }} />
      {isLoggedIn
        ? <LoggedInHome userName={userName} onNavigate={onNavigate} />
        : <LoggedOutHome onNavigate={onNavigate} onRequestLogin={onRequestLogin} />}
    </div>
  );
}

/** 로그인 Home은 스크롤 없이 한 화면(뷰포트)에 들어와야 한다. 좌우 2칼 구성(인사말 카드 | 목표
 *  차량 카드)은 성격이 다른 두 덩어리를 억지로 나란히 붙여놓은 것처럼 어색해 보여 걷어냈다 —
 *  대신 인사말은 카드/테두리 없이 캔버스 배경 위에 가볍게 얹고(물방개+문구를 가로로 묶어 세로
 *  공간을 아낀다), 그 아래 목표 차량 카드 하나만 이어지는 단일 세로 흐름으로 바꿨다. */
function LoggedInHome({ userName, onNavigate }: { userName: string; onNavigate: (s: Screen) => void }) {
  return (
    <main className="flex flex-col items-center px-16 pt-8">
      {/* Portfolio/PortfolioAuto의 "한 화면" 메인 컨텐츠 폭(max-w-[1040px])과 통일한다. */}
      <div className="flex w-full max-w-[1040px] flex-col items-center gap-7">
        <div className="flex items-center gap-6">
          <img src="/character-recommend.png" alt="물방개" className="h-24 w-auto shrink-0 object-contain" />
          <div className="flex flex-col gap-1.5">
            <h1 className="text-[26px] font-bold leading-9 tracking-[-0.02em]">
              {userName}님, 오늘은 무엇을 알아볼까요?
            </h1>
            <p className="text-[15px] text-muted">
              물방개와 함께 투자 전략부터 시장 이야기까지 쉽게 살펴보세요.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button onClick={() => onNavigate('strategy-list')} className="rounded-field bg-lime px-6 py-3.5 text-[15px] font-bold text-navy">
            투자 전략 살펴보기 →
          </button>
          <button
            onClick={() => onNavigate('information')}
            className="rounded-field px-5 py-3.5 text-[15px] font-semibold text-navy shadow-[0_0_0_1px_#E5E9E3_inset] transition-shadow hover:shadow-[0_0_0_1px_#C9D1C4_inset]"
          >
            오늘의 인사이트 보기 →
          </button>
        </div>

        <CarGoalProgress />
      </div>
    </main>
  );
}

/** 비로그인 Home — "기능/성과를 나열하는 페이지"가 아니라, 물방개와 한 문장으로 FE!N이 무엇을
 * 도와주는 서비스인지 바로 알리고 시작 행동(투자성향 진단)으로 보내는 것이 목적이다. */
function LoggedOutHome({ onNavigate, onRequestLogin }: { onNavigate: (s: Screen) => void; onRequestLogin: () => void }) {
  return (
    <main className="flex flex-col items-center pb-24">
      <section className="grid w-[1312px] grid-cols-[1fr_auto] items-center gap-16 px-16 pb-24 pt-20">
        <div className="flex flex-col gap-6">
          <h1 className="text-[56px] font-bold leading-[74px] tracking-[-0.04em]">
            투자는 어려워도,<br />내 전략은 이해할 수 있게.
          </h1>
          <p className="max-w-[540px] text-xl leading-[34px] text-muted">
            내 투자성향에 맞는 전략을 찾고,<br />왜 이 전략인지 쉽게 이해할 수 있어요.
          </p>
          <div className="flex items-center gap-6 pt-3">
            <button onClick={onRequestLogin} className="rounded-field bg-lime px-9 py-5 text-[19px] font-bold text-navy">
              내 투자성향 알아보기 →
            </button>
            <button onClick={() => onNavigate('strategy-list')} className="text-[17px] font-semibold text-muted transition-colors hover:text-navy">
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
              <div className="flex w-[300px] flex-col gap-2">
                <span className="mb-1 flex h-9 w-9 items-center justify-center rounded-full bg-[#F1FBD4] text-[15px] font-bold text-[#3F5222]">
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
  );
}
