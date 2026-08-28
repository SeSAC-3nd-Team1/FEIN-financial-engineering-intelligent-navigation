import CarGoalProgress from '../components/CarGoalProgress';
import Header from '../components/Header';
import { useCarGoal } from '../hooks/useCarGoal';
import { won } from '../lib/validation';
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
 * 00 홈 — 같은 route를 로그인 여부로 분기해서 쓴다.
 * 비로그인: 브랜드 랜딩(Phase 4). 로그인: Header "홈"을 직접 눌렀을 때만 보이는 Personal
 * Navigation Hub(Phase 5) — Portfolio와 역할이 겹치지 않도록 투자 데이터는 전혀 보여주지 않는다.
 * 로그인 직후 자동 랜딩 규칙(Portfolio/입금 요청)은 App.tsx의 navigate()가 그대로 담당하고 있어
 * 여기서는 건드리지 않는다.
 */
export default function Home({ userName, onNavigate }: Props) {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);

  return (
    // Portfolio.tsx와 같은 패턴 — 뷰포트가 넉넉하면 한 화면(h-screen)에 다 담기도록 아래 flex
    // 트리를 가용 높이에 맞춰 나누고, 화면이 작아 다 안 들어가면 페이지 자체가 스크롤된다.
    <div className="flex h-screen flex-col overflow-y-auto bg-canvas">
      <Header active="home" userName={userName} onNavigate={onNavigate} guestCta={{ label: '시작하기', onClick: () => onNavigate('start-signup') }} />
      {isLoggedIn
        ? <LoggedInHome userName={userName} />
        : <LoggedOutHome onNavigate={onNavigate} />}
    </div>
  );
}

/** 로그인 Home은 스크롤 없이 한 화면(뷰포트)에 들어와야 한다. 좌우 2칼 구성(인사말 카드 | 목표
 *  차량 카드)은 성격이 다른 두 덩어리를 억지로 나란히 붙여놓은 것처럼 어색해 보여 걷어냈다 —
 *  대신 인사말은 카드/테두리 없이 캔버스 배경 위에 가볍게 얹고(물방개+문구를 가로로 묶어 세로
 *  공간을 아낀다), 그 아래 목표 차량 카드 하나만 이어지는 단일 세로 흐름으로 바꿨다. Portfolio.tsx와
 *  같은 방식으로 목표 차량 카드가 남는 세로 공간을 flex-1로 채워서(min-h-0 없이는 넘칠 때 부모를
 *  밀어낸다), 카드 아래 빈 캔버스가 그냥 남지 않고 화면 전체를 쓴다. */
function LoggedInHome({ userName }: { userName: string }) {
  // 훅을 여기서 한 번만 불러 인사말 줄 요약과 아래 CarGoalProgress 카드에 같은 값을 내려준다.
  const carGoal = useCarGoal();
  const showSummary = carGoal.status === 'ready' && carGoal.grade !== null;

  return (
    <main className="flex min-h-0 flex-1 flex-col items-center px-16 pb-8 pt-8">
      {/* Portfolio/PortfolioAuto의 "한 화면" 메인 컨텐츠 폭(max-w-[1040px])과 통일한다. */}
      <div className="flex min-h-0 w-full max-w-[1040px] flex-1 flex-col gap-7">
        {/* 인사말 줄도 아래 목표 차량 카드처럼 폭 전체를 쓴다 — 왼쪽 물방개+문구, 오른쪽 끝에는
            내비게이션 버튼(헤더에 이미 있어 중복이었다) 대신 목표/현재 투자 금액을 한눈에
            보여준다 — 아래 카드로 스크롤/시선 이동 없이도 바로 확인 가능하게 한다. */}
        <div className="flex w-full shrink-0 items-center justify-between gap-6">
          <div className="flex items-center gap-6">
            <img src="/character-recommend.png" alt="물방개" className="h-24 w-auto shrink-0 object-contain" />
            <div className="flex flex-col gap-1.5">
              <h1 className="text-[26px] font-bold leading-9 tracking-[-0.02em]">
                {userName}님, 오늘도 목표 차량을 향해 달려볼까요?
              </h1>
              <p className="text-[15px] text-muted">
                물방개와 함께 투자 전략부터 시장 이야기까지 쉽게 살펴보세요.
              </p>
            </div>
          </div>

          {showSummary && (
            <div className="flex shrink-0 items-center gap-8">
              <div className="flex flex-col items-end gap-0.5">
                <span className="text-[13px] text-muted">목표 금액</span>
                <span className="text-xl font-bold tracking-[-0.02em]">{won(carGoal.goalAmount)}</span>
              </div>
              <div className="flex flex-col items-end gap-0.5">
                <span className="text-[13px] text-muted">현재 투자 금액</span>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold tracking-[-0.02em] text-navy">{won(carGoal.currentAmount)}</span>
                  {/* Portfolio.tsx "나의 투자"와 같은 방식(return_rate, 상승 text-up/하락 text-down)으로
                      수익률을 함께 보여준다 — 화면마다 표기가 다르면 같은 계좌 정보를 다르게 읽을 수 있다. */}
                  <span className={`text-sm font-bold ${carGoal.returnPct >= 0 ? 'text-up' : 'text-down'}`}>
                    {carGoal.returnPct >= 0 ? '+' : ''}
                    {carGoal.returnPct.toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        <CarGoalProgress {...carGoal} />
      </div>
    </main>
  );
}

/** 비로그인 Home — "기능/성과를 나열하는 페이지"가 아니라, 물방개와 한 문장으로 FE!N이 무엇을
 * 도와주는 서비스인지 바로 알리고 시작 행동(회원가입)으로 보내는 것이 목적이다. */
function LoggedOutHome({ onNavigate }: { onNavigate: (s: Screen) => void }) {
  return (
    <main className="flex flex-col items-center pb-24">
      <section className="grid w-[1312px] grid-cols-[1fr_auto] items-center gap-16 px-16 pb-24 pt-20">
        <div className="flex flex-col gap-6">
          <h1 className="text-[56px] font-bold leading-[74px] tracking-[-0.04em]">
            투자는 어려워도,<br />내 전략은 이해할 수 있게.
          </h1>
          <p className="max-w-[540px] text-xl leading-[34px] text-muted">
            내 투자성향을 이해하고,<br />다양한 투자전략을 비교해 직접 선택할 수 있어요.
          </p>
          <div className="flex items-center gap-6 pt-3">
            <button onClick={() => onNavigate('start-signup')} className="rounded-field bg-lime px-9 py-5 text-[19px] font-bold text-navy">
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
