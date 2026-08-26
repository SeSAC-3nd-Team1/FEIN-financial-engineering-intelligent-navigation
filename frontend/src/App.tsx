import { useEffect, useRef, useState } from 'react';
import AllHoldings from './pages/AllHoldings';
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
import PortfolioAuto from './pages/PortfolioAuto';
import PortfolioDetail from './pages/PortfolioDetail';
import RebalanceAlerts from './pages/RebalanceAlerts';
import RiskProfile from './pages/RiskProfile';
import RiskResult from './pages/RiskResult';
import SignupStep1 from './pages/SignupStep1';
import SignupStep2 from './pages/SignupStep2';
import SignupStep3 from './pages/SignupStep3';
import StartInvesting from './pages/StartInvesting';
import StockDetail from './pages/StockDetail';
import StrategyDetail from './pages/StrategyDetail';
import TransactionDetail from './pages/TransactionDetail';
import TransactionHistory from './pages/TransactionHistory';
import { STRATEGIES } from './data/strategies';
import { toAccountOperationMode, type OperationMode } from './data/fees';
import { analyzeInvestorProfileApi, signupTermsApi } from './lib/backendApi';
import { buildInvestorAnswerPayload } from './lib/investorProfile';
import { resolveInvestmentEntryStep, resolvePreviousStep, type InvestmentEntryStep } from './lib/investmentFlow';
import { useAuthStore } from './store/authStore';
import { useInvestmentStore } from './store/investmentStore';
import { useTradingStore } from './store/tradingStore';
import type { Screen, SignupPersonal } from './types';

/** 새로고침해도 유지할 최소한의 내비게이션 상태 — sessionStorage 에 저장한다(탭을 닫으면 사라짐).
 *  회원가입 입력값처럼 민감하거나 오래 들고 있을 필요 없는 값은 여기 포함하지 않는다.
 *  사용자별로 분리된 키가 아니라, 로그아웃 시 authStore.logout()/initialize() 이 이 키를 함께 지운다
 *  (같은 브라우저에서 다른 사용자가 로그인해도 이전 사용자의 화면 상태를 이어받지 않도록). */
const SESSION_KEY = 'fein.session-nav';
interface PersistedNav {
  screen: Screen; strategyId: string; stockCode: string; stockBackTarget: Screen;
  selectedTransactionId: string; transactionBackTarget: Screen;
}
function loadPersistedNav(): Partial<PersistedNav> {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Partial<PersistedNav>) : {};
  } catch {
    return {};
  }
}
/** 로그인이 필요한 화면 — 새로고침 후 토큰이 없거나 만료된 걸로 확인되면 이 화면들에서는 로그인으로 돌려보낸다.
 *  투자 시작 Flow(invest-*) 화면들도 로그인 이후에만 진입 가능한 흐름이라 함께 포함한다. */
const PROTECTED_SCREENS: Screen[] = [
  'dashboard', 'portfolio', 'portfolio-detail', 'stock', 'strategy', 'start', 'transactions', 'transaction-detail',
  'rebalance-alerts', 'all-holdings', 'invest-terms', 'invest-account', 'invest-deposit', 'invest-confirm',
];

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
  // screen/strategyId/stockCode/stockBackTarget 은 새로고침 직후 첫 렌더에서 sessionStorage 값으로
  // 곧바로 초기화한다(useState lazy initializer) — 그래야 'home' 으로 한 번 그렸다가 다시 튀는 깜빡임이 없다.
  const [persistedNav] = useState(loadPersistedNav);
  const [screen, setScreen] = useState<Screen>(persistedNav.screen ?? 'home');
  const [personal, setPersonal] = useState<SignupPersonal>({
    name: '', birthdate: '', phone: '', aiPersonalizationConsent: false,
    agreements: { a1: false, a2: false, a3: false, a4: false, b: false, c: false, ai: false },
  });
  // 전략 선택은 strategyId(=STRATEGIES 의 id) 하나만 상태로 두고, 화면별 표시 이름은 여기서 파생시킨다.
  // (과거엔 strategyId 와 별도로 strategy 표시 이름을 따로 들고 있어, 전략 선택 후에도
  //  StartInvesting/Portfolio 가 갱신되지 않는 불일치가 있었다.)
  const [strategyId, setStrategyId] = useState<string>(persistedNav.strategyId ?? 'low');
  const strategy = STRATEGIES.find((s) => s.id === strategyId) ?? STRATEGIES[0];
  const [stockCode, setStockCode] = useState(persistedNav.stockCode ?? '005930');
  // 종목 상세 진입 지점에 따라 뒤로가기 목적지가 달라진다 (start 에서 왔으면 start로, portfolio 에서 왔으면 portfolio-detail로)
  const [stockBackTarget, setStockBackTarget] = useState<Screen>(persistedNav.stockBackTarget ?? 'portfolio-detail');
  // 거래 상세 진입 지점(포트폴리오 상세의 "최근 거래" 3건 vs 전체 거래 내역)에 따라 뒤로가기 목적지가 달라진다.
  const [selectedTransactionId, setSelectedTransactionId] = useState(persistedNav.selectedTransactionId ?? '');
  const [transactionBackTarget, setTransactionBackTarget] = useState<Screen>(persistedNav.transactionBackTarget ?? 'portfolio-detail');
  // 투자자 정보 확인(risk) 완료 후 어디로 이어갈지 + 진입 맥락(안내 문구)
  const [postDiagnosisTarget, setPostDiagnosisTarget] = useState<Screen>('risk-result');
  const [riskNotice, setRiskNotice] = useState<string | undefined>(undefined);
  // 투자 시작 Flow(약관 → 계좌 준비 → 입금 → 최종 확인) 동안 유지해야 하는 선택 금액/운용방식
  // 기본값은 "자동으로 운용" — 처음 투자하는 사용자에게 이 방식을 우선 추천하는 정책
  const [investmentAmount, setInvestmentAmount] = useState(1_000_000);
  const [investmentMode, setInvestmentMode] = useState<OperationMode>('auto');
  const register = useAuthStore((s) => s.register);
  const initialize = useAuthStore((s) => s.initialize);
  const authenticatedUser = useAuthStore((s) => s.user);
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);
  const isHydrating = useAuthStore((s) => s.isHydrating);
  const investorProfileCompleted = useAuthStore((s) => s.investorProfileCompleted);
  const completeInvestorProfile = useAuthStore((s) => s.completeInvestorProfile);
  const accessToken = useAuthStore((s) => s.accessToken);
  const ensureAccount = useTradingStore((s) => s.ensureAccount);
  const termsAcceptedStrategyIds = useInvestmentStore((s) => s.termsAcceptedStrategyIds);
  const accountsByMode = useInvestmentStore((s) => s.accountsByMode);
  // 운용방식은 같은 계좌를 공유할 수 없어(정책), "지금 선택된 운용방식의 계좌"만 이 이름으로 다룬다
  const sesacAccount = accountsByMode[investmentMode] ?? null;
  // StrategyDetail의 "입금이 필요해요" 배너 렌더링용 — navigate('portfolio')의 리다이렉트 판단은
  // 타이밍 이슈 때문에 별도로 getState()에서 직접 읽는다(위 주석 참고), 여기 반응형 값은 렌더링 전용
  const pendingInvestment = useInvestmentStore((s) => s.pendingInvestment);
  const activeMode = useInvestmentStore((s) => s.activeMode);
  const acceptStrategyTerms = useInvestmentStore((s) => s.acceptStrategyTerms);
  const connectSesacAccount = useInvestmentStore((s) => s.connectSesacAccount);
  const deposit = useInvestmentStore((s) => s.deposit);
  const deferDeposit = useInvestmentStore((s) => s.deferDeposit);
  const hydrateForUser = useInvestmentStore((s) => s.hydrateForUser);
  const setInFlightStep = useInvestmentStore((s) => s.setInFlightStep);
  const clearInFlight = useInvestmentStore((s) => s.clearInFlight);
  const setActiveMode = useInvestmentStore((s) => s.setActiveMode);

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

  /**
   * StartInvesting "이대로 시작하기" — 이미 완료한 단계는 건너뛰고 다음 필요한 단계로 이동한다.
   * 방금 고른 mode가 지금까지의 investmentMode와 다를 수 있으므로(운용방식 전환 시도), 클로저의
   * sesacAccount(현재 investmentMode 기준)를 그대로 쓰면 안 되고 mode에 맞는 계좌를 다시 찾아야 한다.
   */
  const enterInvestmentFlow = (amount: number, mode: OperationMode) => {
    const accountForMode = accountsByMode[mode] ?? null;
    const step = resolveInvestmentEntryStep({ strategyId, amount, termsAcceptedStrategyIds, sesacAccount: accountForMode });
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
  // 직전 렌더의 로그인 사용자 id — 로그아웃(비로그인으로 전환)을 감지해 화면 상태를 초기화하는 데만 쓴다.
  // 최초 마운트 시(아직 initialize() 가 안 끝나 null → null 로 시작하는 순간)에는 건드리지 않아야
  // 새로고침 복원(sessionStorage 에서 그대로 이어받기)이 깨지지 않는다.
  const prevUserIdRef = useRef<string | null>(null);

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
    const currentUserId = authenticatedUser?.user_id ?? null;
    hydrateForUser(currentUserId);
    // sessionStorage 의 nav 키는 사용자별로 분리돼 있지 않다(authStore.logout 이 로그아웃 시 통째로 지운다).
    // 그래도 React state 는 메모리에 남아있어서, 로그인 상태였다가(prevUserIdRef 가 non-null) 로그아웃으로
    // 전환된 순간(currentUserId 가 null)에는 다음 로그인 사용자가 이전 사용자의 전략/종목 선택을
    // 이어받지 않도록 화면 상태를 기본값으로 되돌린다. 최초 마운트(null → null/user 로 시작)에는 건드리지 않는다.
    if (prevUserIdRef.current && !currentUserId) {
      setScreen('home');
      setStrategyId('low');
      setStockCode('005930');
      setStockBackTarget('portfolio-detail');
      setSelectedTransactionId('');
      setTransactionBackTarget('portfolio-detail');
    }
    prevUserIdRef.current = currentUserId;
  }, [authenticatedUser?.user_id, hydrateForUser]);

  // 새로고침해도 같은 화면에 남아있도록 내비게이션 상태를 sessionStorage 에 계속 동기화한다.
  useEffect(() => {
    const nav: PersistedNav = {
      screen, strategyId, stockCode, stockBackTarget, selectedTransactionId, transactionBackTarget,
    };
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(nav));
  }, [screen, strategyId, stockCode, stockBackTarget, selectedTransactionId, transactionBackTarget]);

  // 로그인이 필요한 화면을 새로고침으로 복원했는데, 토큰 검증(initialize)이 끝난 뒤
  // 실제로는 로그인 상태가 아닌 것으로 확인되면(토큰 만료 등) 로그인 화면으로 돌려보낸다.
  useEffect(() => {
    if (!isHydrating && !isLoggedIn && PROTECTED_SCREENS.includes(screen)) {
      setScreen('login');
    }
  }, [isHydrating, isLoggedIn, screen]);

  // 거래 상세를 새로고침으로 복원했는데 selectedTransactionId 를 복원할 수 없으면(예: 이 필드가 없던
  // 이전 버전의 sessionStorage) "거래 내역을 찾을 수 없어요" 대신 전체 거래 내역으로 보낸다.
  useEffect(() => {
    if (screen === 'transaction-detail' && !selectedTransactionId) {
      setScreen('transactions');
    }
  }, [screen, selectedTransactionId]);

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
            // 백엔드에도 실제로 저장을 시도한다(investor_profile_assessments) — AI 분석이라 시간이
            // 걸리고, AI_PERSONALIZATION 약관 비동의/일시 오류로 실패할 수도 있다. 화면 전환은 이미
            // 위에서 로컬 결과로 끝났으니, 실패해도 사용자 흐름을 막지 않는 best-effort 로 둔다.
            if (accessToken) {
              void analyzeInvestorProfileApi(
                { questionnaire_version: 'v1', answers: buildInvestorAnswerPayload(answers) },
                accessToken,
              ).catch(() => undefined);
            }
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
              // InvestDeposit과 동일하게, 이미 보유한 잔액(대기 중인 투자와 같은 운용방식 계좌 기준)을 제외한 부족분만 안내한다
              ? { amount: Math.max(0, pendingInvestment.amount - (accountsByMode[pendingInvestment.mode]?.balance ?? 0)) }
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
          onSelectStock={(code) => { setStockCode(code); setStockBackTarget('start'); setScreen('stock'); }}
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
          mode={investmentMode}
          otherModeAccount={(() => {
            const otherMode: OperationMode = investmentMode === 'auto' ? 'manual' : 'auto';
            const otherAccount = accountsByMode[otherMode];
            return otherAccount ? { mode: otherMode, accountNumber: otherAccount.accountNumber } : null;
          })()}
          onNavigate={navigate}
          onBack={() => goBackInInvestmentFlow('invest-account')}
          onComplete={(account) => {
            connectSesacAccount(investmentMode, account);
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
            deposit(investmentMode, shortfall);
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
            await ensureAccount(accessToken, strategyId, toAccountOperationMode(investmentMode));
            setActiveMode(investmentMode);
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
          mode={activeMode}
          onNavigate={navigate}
          onOpenHoldings={() => navigate('portfolio-detail')}
          onChangeStrategy={() => navigate('portfolio-detail')}
        />
      )}

      {/* 운용방식(activeMode)에 따라 요약 화면을 다르게 보여준다 — 반자동은 AI 제안을 사용자가 승인해야 하는
          Portfolio.tsx, 자동매매는 AI가 이미 실행을 마친 PortfolioAuto.tsx. 계좌를 아직 안 만든 경우(null)는
          기존 기본값인 반자동으로 보여준다. */}
      {screen === 'portfolio' && (
        activeMode === 'auto' ? (
          <PortfolioAuto
            userName={userName}
            onNavigate={setScreen}
            onOpenDetail={() => setScreen('portfolio-detail')}
          />
        ) : (
          <Portfolio
            userName={userName}
            onNavigate={setScreen}
            onOpenDetail={() => setScreen('portfolio-detail')}
            onStartRiskProfile={() => startInvestorProfile('risk-result')}
          />
        )
      )}

      {screen === 'portfolio-detail' && (
        <PortfolioDetail
          userName={userName}
          strategyId={strategyId}
          onStrategyChange={setStrategyId}
          onNavigate={navigate}
          onSelectStock={(code) => { setStockCode(code); setStockBackTarget('portfolio-detail'); setScreen('stock'); }}
          onSelectTransaction={(id) => {
            setSelectedTransactionId(id);
            setTransactionBackTarget('portfolio-detail');
            setScreen('transaction-detail');
          }}
          onRediagnose={() => startInvestorProfile('risk-result')}
          onBack={() => setScreen('portfolio')}
        />
      )}

      {screen === 'rebalance-alerts' && (
        <RebalanceAlerts
          userName={userName}
          strategyId={strategyId}
          onNavigate={navigate}
          onBack={() => setScreen('portfolio-detail')}
        />
      )}

      {screen === 'all-holdings' && (
        <AllHoldings
          userName={userName}
          onNavigate={navigate}
          onSelectStock={(code) => { setStockCode(code); setStockBackTarget('all-holdings'); setScreen('stock'); }}
          onBack={() => setScreen('portfolio-detail')}
        />
      )}

      {screen === 'transactions' && (
        <TransactionHistory
          userName={userName}
          onNavigate={setScreen}
          onSelectTransaction={(id) => {
            setSelectedTransactionId(id);
            setTransactionBackTarget('transactions');
            setScreen('transaction-detail');
          }}
          onBack={() => setScreen('portfolio-detail')}
        />
      )}

      {screen === 'transaction-detail' && (
        <TransactionDetail
          transactionId={selectedTransactionId}
          backTarget={transactionBackTarget}
          userName={userName}
          onNavigate={setScreen}
          onBack={() => setScreen(transactionBackTarget)}
        />
      )}

      {screen === 'stock' && (
        <StockDetail
          stockCode={stockCode}
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
