import { useEffect, useRef, useState } from 'react';
import Chatbot from './components/Chatbot';
import Dashboard from './pages/Dashboard';
import Home from './pages/Home';
import InformationExam from './pages/InformationExam';
import InvestAccount from './pages/InvestAccount';
import InvestConfirm from './pages/InvestConfirm';
import InvestDeposit from './pages/InvestDeposit';
import InvestorProfileCheck from './pages/InvestorProfileCheck';
import InvestTerms from './pages/InvestTerms';
import Login from './pages/Login';
import Portfolio from './pages/Portfolio';
import RiskProfile from './pages/RiskProfile';
import RiskResult from './pages/RiskResult';
import SignupStep1 from './pages/SignupStep1';
import SignupStep2 from './pages/SignupStep2';
import SignupStep3 from './pages/SignupStep3';
import StartInvesting from './pages/StartInvesting';
import StockDetail from './pages/StockDetail';
import StrategyDetail from './pages/StrategyDetail';
import { STRATEGIES } from './data/strategies';
import type { OperationMode } from './data/fees';
import { signupTermsApi } from './lib/backendApi';
import { resolveInvestmentEntryStep, resolvePreviousStep, type InvestmentEntryStep } from './lib/investmentFlow';
import { useAuthStore } from './store/authStore';
import { useInvestmentStore } from './store/investmentStore';
import { useTradingStore } from './store/tradingStore';
import type { Screen, SignupPersonal } from './types';

/** 투자 시작 Flow(약관~최종확인) 화면 목록 — Header 등으로 이 밖으로 나가면 inFlight(새로고침 복원용 진행 상태)를 정리한다 */
const INVEST_FLOW_SCREENS: Screen[] = ['invest-terms', 'invest-account', 'invest-deposit', 'invest-confirm'];

/**
 * 라우팅 상태 머신 — 전체 사용자 흐름
 *
 *   home → login → signup-1 → signup-2 → signup-3
 *        → risk(투자자 정보 확인 · 인트로·Q1~Q7·완료) → risk-result(투자성향 결과 + 전략 추천)
 *        → strategy → start → portfolio(20종목) → stock(종목 상세)
 *   information 은 헤더 "정보"에서 언제든 진입
 *
 *   로그인 성공, 투자 시작 완료, 헤더 "나의 포트폴리오" 클릭은 모두 동일하게
 *   portfolio(Power BI 분석 대시보드)로 착지한다. dashboard 는 portfolio 상단의
 *   "← 대시보드로 돌아가기"로만 진입하는 보조 요약 화면이다.
 *
 *   실제 투자 시작(strategy → start)은 investorProfileCompleted 가드를 거친다:
 *   완료 상태면 investor-check(정보 확인)로, 미완료면 안내와 함께 risk로 보낸다.
 *   두 경우 모두 목적지(start)를 postDiagnosisTarget 에 기억해뒀다가 완료/확인 후 이어간다.
 *
 * 챗봇 FAB 는 라우팅 밖에 있어 모든 화면에 상주한다.
 */
export default function App() {
  const [screen, setScreen] = useState<Screen>('home');
  const [personal, setPersonal] = useState<SignupPersonal>({
    name: '', birthdate: '', phone: '', aiPersonalizationConsent: false,
    agreements: { a1: false, a2: false, a3: false, a4: false, b: false, c: false, ai: false },
  });
  // 전략 선택은 strategyId(=STRATEGIES 의 id) 하나만 상태로 두고, 화면별 표시 이름은 여기서 파생시킨다.
  // (과거엔 strategyId 와 별도로 strategy 표시 이름을 따로 들고 있어, 전략 선택 후에도
  //  StartInvesting/Portfolio 가 갱신되지 않는 불일치가 있었다.)
  const [strategyId, setStrategyId] = useState<string>('low');
  const strategy = STRATEGIES.find((s) => s.id === strategyId) ?? STRATEGIES[0];
  const [stockIndex, setStockIndex] = useState(0);
  // 종목 상세 진입 지점에 따라 뒤로가기 목적지가 달라진다 (start 에서 왔으면 start로, portfolio 에서 왔으면 portfolio로)
  const [stockBackTarget, setStockBackTarget] = useState<Screen>('portfolio');
  // 투자자 정보 확인(risk) 완료 후 어디로 이어갈지 + 진입 맥락(안내 문구)
  const [postDiagnosisTarget, setPostDiagnosisTarget] = useState<Screen>('risk-result');
  const [riskNotice, setRiskNotice] = useState<string | undefined>(undefined);
  // 투자 시작 Flow(약관 → 계좌 준비 → 입금 → 최종 확인) 동안 유지해야 하는 선택 금액/운용방식
  const [investmentAmount, setInvestmentAmount] = useState(1_000_000);
  const [investmentMode, setInvestmentMode] = useState<OperationMode>('manual');
  const register = useAuthStore((s) => s.register);
  const initialize = useAuthStore((s) => s.initialize);
  const authenticatedUser = useAuthStore((s) => s.user);
  const investorProfileCompleted = useAuthStore((s) => s.investorProfileCompleted);
  const completeInvestorProfile = useAuthStore((s) => s.completeInvestorProfile);
  const accessToken = useAuthStore((s) => s.accessToken);
  const ensureAccount = useTradingStore((s) => s.ensureAccount);
  const termsAcceptedStrategyIds = useInvestmentStore((s) => s.termsAcceptedStrategyIds);
  const sesacAccount = useInvestmentStore((s) => s.sesacAccount);
  // StrategyDetail의 "입금이 필요해요" 배너 렌더링용 — navigate('portfolio')의 리다이렉트 판단은
  // 타이밍 이슈 때문에 별도로 getState()에서 직접 읽는다(위 주석 참고), 여기 반응형 값은 렌더링 전용
  const pendingInvestment = useInvestmentStore((s) => s.pendingInvestment);
  const acceptStrategyTerms = useInvestmentStore((s) => s.acceptStrategyTerms);
  const connectSesacAccount = useInvestmentStore((s) => s.connectSesacAccount);
  const deposit = useInvestmentStore((s) => s.deposit);
  const deferDeposit = useInvestmentStore((s) => s.deferDeposit);
  const hydrateForUser = useInvestmentStore((s) => s.hydrateForUser);
  const setInFlightStep = useInvestmentStore((s) => s.setInFlightStep);
  const clearInFlight = useInvestmentStore((s) => s.clearInFlight);

  /**
   * invest-terms~invest-confirm 중 한 화면으로 이동할 때 항상 이 함수를 거친다.
   * strategyId/금액/운용방식을 항상 함께 동기화해서 화면에 보이는 값과 새로고침 복원용
   * inFlight 기록이 어긋나지 않게 한다(호출부마다 따로 setStrategyId 등을 챙길 필요 없음).
   */
  const enterInvestmentStep = (step: InvestmentEntryStep, ctxStrategyId: string, ctxAmount: number, ctxMode: OperationMode) => {
    setStrategyId(ctxStrategyId);
    setInvestmentAmount(ctxAmount);
    setInvestmentMode(ctxMode);
    setInFlightStep({ step, strategyId: ctxStrategyId, amount: ctxAmount, mode: ctxMode });
    setScreen(step);
  };

  /** StartInvesting "이대로 시작하기" — 이미 완료한 단계는 건너뛰고 다음 필요한 단계로 이동한다 */
  const enterInvestmentFlow = (amount: number, mode: OperationMode) => {
    const step = resolveInvestmentEntryStep({ strategyId, amount, termsAcceptedStrategyIds, sesacAccount });
    enterInvestmentStep(step, strategyId, amount, mode);
  };

  /**
   * 투자 Flow 화면들의 "이전으로" — 고정된 이전 화면이 아니라, 현재 상태 기준으로 아직 필요한
   * 가장 가까운 이전 단계로 돌아간다. 더 돌아갈 단계가 없으면(이미 완료된 상태로 이 화면에
   * 들어온 경우) 금액 선택 화면('start')으로 나가고, 그 시점에 inFlight도 정리한다.
   */
  const goBackInInvestmentFlow = (currentStep: InvestmentEntryStep) => {
    const prev = resolvePreviousStep(currentStep, { strategyId, amount: investmentAmount, termsAcceptedStrategyIds, sesacAccount });
    if (prev === 'start') {
      clearInFlight();
      setScreen('start');
    } else {
      enterInvestmentStep(prev, strategyId, investmentAmount, investmentMode);
    }
  };

  /**
   * Header "나의 포트폴리오"/로그인 성공 등 Portfolio로 향하는 모든 경로가 거치는 관문.
   * DEPOSIT_PENDING(계좌는 연결됐지만 입금이 남은) 상태라면 Portfolio 대신 입금 요청 화면으로 보낸다.
   * 투자 Flow 화면에서 그 밖의 목적지(정보/전략 둘러보기 등)로 명시적으로 이동할 때는
   * inFlight(새로고침 복원용 진행 상태)를 정리한다 — "나중에 입금할게요"의 pendingInvestment는 별개로 유지된다.
   *
   * 로그인 직후에는 Login.tsx가 login() 완료와 동시에 이 함수를 동기적으로 호출하는데, 이 시점엔
   * "사용자별 hydrate" useEffect가 아직 커밋되지 않았을 수 있다(리액트 이펙트는 렌더 이후 실행).
   * 그래서 반응형 클로저 값(pendingInvestment)을 믿는 대신, 여기서 현재 로그인된 사용자 기준으로
   * 강제로 다시 hydrate한 뒤 스토어에서 바로 최신 값을 읽는다.
   */
  const navigate = (target: Screen) => {
    if (target === 'portfolio') {
      const userId = useAuthStore.getState().user?.user_id ?? null;
      hydrateForUser(userId);
      const pending = useInvestmentStore.getState().pendingInvestment;
      if (pending) {
        enterInvestmentStep('invest-deposit', pending.strategyId, pending.amount, pending.mode);
        return;
      }
    }
    if (INVEST_FLOW_SCREENS.includes(screen) && !INVEST_FLOW_SCREENS.includes(target)) {
      clearInFlight();
    }
    setScreen(target);
  };

  const userName = authenticatedUser?.name ?? (personal.name.trim() || '서연');

  const hasRestoredInvestFlowRef = useRef(false);

  // 앱 최초 로드(새로고침 포함) — 토큰이 있으면 로그인 사용자를 복원하고, 그 사용자의 투자 Flow가
  // invest-terms~invest-confirm 중간에 있었다면 화면/선택값(strategyId·금액·운용방식)까지 그대로 복원한다.
  useEffect(() => {
    (async () => {
      await initialize();
      const userId = useAuthStore.getState().user?.user_id ?? null;
      hydrateForUser(userId);
      if (!hasRestoredInvestFlowRef.current) {
        hasRestoredInvestFlowRef.current = true;
        const restored = useInvestmentStore.getState().inFlight;
        if (restored) {
          setStrategyId(restored.strategyId);
          setInvestmentAmount(restored.amount);
          setInvestmentMode(restored.mode);
          setScreen(restored.step);
        }
      }
    })();
  }, [initialize, hydrateForUser]);

  // 세션 중 로그인/로그아웃으로 사용자가 바뀔 때마다 해당 사용자의 저장된 상태로 다시 hydrate한다.
  // (화면 복원은 위 최초 로드 시점에만 하고, 로그인 직후 명시적 이동(navigate('portfolio') 등)과는 겹치지 않게 한다)
  useEffect(() => {
    hydrateForUser(authenticatedUser?.user_id ?? null);
  }, [authenticatedUser?.user_id, hydrateForUser]);

  /** risk 화면 진입 지점 — 완료 후 목적지와 안내 문구를 함께 정한다 */
  const startInvestorProfile = (target: Screen, opts?: { notice?: string }) => {
    setPostDiagnosisTarget(target);
    setRiskNotice(opts?.notice);
    setScreen('risk');
  };

  /** StrategyDetail "이 전략으로 시작하기" — 실제 투자 실행 전 투자자 정보 확인 가드 */
  const handleStartInvesting = () => {
    if (investorProfileCompleted) {
      setScreen('investor-check');
    } else {
      startInvestorProfile('start', { notice: '투자를 시작하기 전에 투자자 정보를 확인해주세요.' });
    }
  };

  return (
    <div className="min-h-screen bg-canvas">
      {screen === 'home' && <Home onNavigate={navigate} />}

      {screen === 'login' && (
        <Login
          // 로그인 성공 → 인증 state를 켜고, 헤더 "나의 포트폴리오"와 동일한 목적지(Portfolio)로 이동
          onLogin={() => navigate('portfolio')}
          onSignup={() => setScreen('signup-1')}
          onHome={() => setScreen('home')}
          onNavigate={navigate}
        />
      )}

      {screen === 'signup-1' && (
        <SignupStep1
          value={personal}
          onChange={setPersonal}
          onNext={() => setScreen('signup-2')}
          userName={userName}
          onNavigate={navigate}
        />
      )}
      {screen === 'signup-2' && (
        <SignupStep2
          phone={personal.phone}
          onNext={() => setScreen('signup-3')}
          onBack={() => setScreen('signup-1')}
          userName={userName}
          onNavigate={navigate}
        />
      )}
      {screen === 'signup-3' && (
        <SignupStep3
          // 가입 API 성공 후 JWT 로그인까지 완료하고 투자자 정보 확인으로 이동한다.
          onComplete={async (userId, password, email) => {
            const termCodeByAgreement = {
              a1: 'A1_THIRD_PARTY',
              a2: 'A2_UNIQUE_ID',
              a3: 'A3_CARRIER',
              a4: 'A4_KCB',
              b: 'B_PRIVACY',
              c: 'C_ASSOCIATE_TERMS',
              ai: 'AI_PERSONALIZATION',
            } as const;
            const agreementByTermCode = Object.fromEntries(
              Object.entries(termCodeByAgreement).map(([key, code]) => [
                code,
                personal.agreements[key as keyof typeof termCodeByAgreement],
              ]),
            );
            const terms = await signupTermsApi();
            await register({
              user_id: userId,
              password,
              name: personal.name.trim(),
              birthdate: personal.birthdate,
              phone_number: personal.phone,
              email,
              phone_verified: true,
              email_verified: true,
              agreements: terms.map((term) => ({
                term_code: term.term_code,
                version: term.version,
                agreed: agreementByTermCode[term.term_code] ?? false,
              })),
            });
            startInvestorProfile('risk-result');
          }}
          onBack={() => setScreen('signup-2')}
          userName={userName}
          onNavigate={navigate}
        />
      )}

      {screen === 'risk' && (
        <RiskProfile
          notice={riskNotice}
          onComplete={({ investorType, answers }) => {
            completeInvestorProfile(investorType, answers, new Date().toISOString());
            setRiskNotice(undefined);
            setScreen(postDiagnosisTarget);
            setPostDiagnosisTarget('risk-result');
          }}
          onExit={() => setScreen('home')}
        />
      )}
      {screen === 'risk-result' && (
        <RiskResult
          userName={userName}
          onNavigate={navigate}
          onSelectStrategy={(id) => { setStrategyId(id); setScreen('strategy'); }}
        />
      )}
      {screen === 'investor-check' && (
        <InvestorProfileCheck
          userName={userName}
          onNavigate={navigate}
          onContinue={() => setScreen('start')}
          onRediagnose={() => startInvestorProfile('start')}
        />
      )}

      {screen === 'strategy' && (
        <StrategyDetail
          strategyId={strategyId}
          userName={userName}
          onNavigate={navigate}
          onStart={handleStartInvesting}
          pendingDeposit={
            pendingInvestment && pendingInvestment.strategyId === strategyId
              // InvestDeposit과 동일하게, 이미 보유한 잔액을 제외한 부족분만 안내한다
              ? { amount: Math.max(0, pendingInvestment.amount - (sesacAccount?.balance ?? 0)) }
              : null
          }
          onResumeDeposit={() => {
            if (!pendingInvestment) return;
            enterInvestmentStep('invest-deposit', pendingInvestment.strategyId, pendingInvestment.amount, pendingInvestment.mode);
          }}
        />
      )}
      {screen === 'start' && (
        <StartInvesting
          userName={userName}
          strategyName={strategy.name}
          onNavigate={navigate}
          onStart={enterInvestmentFlow}
          onSelectStock={(i) => { setStockIndex(i); setStockBackTarget('start'); setScreen('stock'); }}
        />
      )}
      {screen === 'invest-terms' && (
        <InvestTerms
          userName={userName}
          strategy={strategy}
          amount={investmentAmount}
          mode={investmentMode}
          onNavigate={navigate}
          onBack={() => goBackInInvestmentFlow('invest-terms')}
          onComplete={() => {
            acceptStrategyTerms(strategyId);
            const step = resolveInvestmentEntryStep({
              strategyId,
              amount: investmentAmount,
              termsAcceptedStrategyIds: [...termsAcceptedStrategyIds, strategyId],
              sesacAccount,
            });
            enterInvestmentStep(step, strategyId, investmentAmount, investmentMode);
          }}
        />
      )}
      {screen === 'invest-account' && (
        <InvestAccount
          userName={userName}
          strategyName={strategy.name}
          onNavigate={navigate}
          onBack={() => goBackInInvestmentFlow('invest-account')}
          onComplete={(account) => {
            connectSesacAccount(account);
            const step = resolveInvestmentEntryStep({
              strategyId, amount: investmentAmount, termsAcceptedStrategyIds, sesacAccount: account,
            });
            enterInvestmentStep(step, strategyId, investmentAmount, investmentMode);
          }}
        />
      )}
      {screen === 'invest-deposit' && sesacAccount && (
        <InvestDeposit
          userName={userName}
          strategyName={strategy.name}
          amount={investmentAmount}
          mode={investmentMode}
          account={sesacAccount}
          onNavigate={navigate}
          onBack={() => goBackInInvestmentFlow('invest-deposit')}
          onDeposit={(shortfall) => {
            deposit(shortfall);
            const step = resolveInvestmentEntryStep({
              strategyId,
              amount: investmentAmount,
              termsAcceptedStrategyIds,
              sesacAccount: { ...sesacAccount, balance: sesacAccount.balance + shortfall },
            });
            enterInvestmentStep(step, strategyId, investmentAmount, investmentMode);
          }}
          onDeferDeposit={() => {
            // Home 은 비로그인 전용 랜딩이라 로그인 상태가 반영되지 않는다 — 전략 상세로 돌려보낸다
            // (Header에 로그인 상태가 정상 표시되고, 필요하면 "이 전략으로 시작하기"로 바로 이 화면에 재진입할 수 있다)
            deferDeposit({ strategyId, strategyName: strategy.name, amount: investmentAmount, mode: investmentMode });
            clearInFlight();
            setScreen('strategy');
          }}
        />
      )}
      {screen === 'invest-confirm' && sesacAccount && (
        <InvestConfirm
          userName={userName}
          strategyName={strategy.name}
          amount={investmentAmount}
          mode={investmentMode}
          account={sesacAccount}
          onNavigate={navigate}
          onBack={() => goBackInInvestmentFlow('invest-confirm')}
          onConfirm={async () => {
            if (!accessToken) {
              setScreen('login');
              throw new Error('로그인이 필요합니다.');
            }
            await ensureAccount(accessToken, strategyId);
            clearInFlight();
            setScreen('portfolio');
          }}
        />
      )}

      {screen === 'information' && <InformationExam userName={userName} onNavigate={navigate} />}

      {screen === 'dashboard' && (
        <Dashboard
          userName={userName}
          strategyName={strategy.name}
          onNavigate={navigate}
          onOpenHoldings={() => navigate('portfolio')}
          onChangeStrategy={() => navigate('portfolio')}
        />
      )}

      {screen === 'portfolio' && (
        <Portfolio
          userName={userName}
          strategyId={strategyId}
          onStrategyChange={setStrategyId}
          onNavigate={navigate}
          onSelectStock={(i) => { setStockIndex(i); setStockBackTarget('portfolio'); setScreen('stock'); }}
          onRediagnose={() => startInvestorProfile('risk-result')}
          onBack={() => setScreen('dashboard')}
        />
      )}

      {screen === 'stock' && (
        <StockDetail
          index={stockIndex}
          userName={userName}
          onNavigate={navigate}
          onBack={() => setScreen(stockBackTarget)}
        />
      )}

      {/* 전 화면 상주 플로팅 챗봇 */}
      <Chatbot />
    </div>
  );
}
