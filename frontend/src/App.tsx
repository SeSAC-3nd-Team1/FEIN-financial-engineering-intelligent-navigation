import { useEffect, useRef, useState } from "react";
import AllHoldings from "./pages/AllHoldings";
import AccountDeposit from "./pages/AccountDeposit";
import AccountSetup from "./pages/AccountSetup";
import Chatbot from "./components/Chatbot";
import Dashboard from "./pages/Dashboard";
import FundAddAmount from "./pages/FundAddAmount";
import FundAddConfirm from "./pages/FundAddConfirm";
import FundOperationResult from "./pages/FundOperationResult";
import FundWithdrawAmount from "./pages/FundWithdrawAmount";

import FundWithdrawConfirm from "./pages/FundWithdrawConfirm";
import Home from "./pages/Home";
import InformationExam from "./pages/InformationExam";
import InvestAccount from "./pages/InvestAccount";
import InvestConfirm from "./pages/InvestConfirm";
import InvestDeposit from "./pages/InvestDeposit";
import InvestorProfileCheck from "./pages/InvestorProfileCheck";
import InvestTerms from "./pages/InvestTerms";
import Login from "./pages/Login";
import type { LoginContext } from "./pages/Login";
import Portfolio from "./pages/Portfolio";
import PortfolioAuto from "./pages/PortfolioAuto";
import PortfolioDetail from "./pages/PortfolioDetail";
import RebalanceAlerts from "./pages/RebalanceAlerts";
import RiskProfile from "./pages/RiskProfile";
import RiskResult from "./pages/RiskResult";
import SignupStep1 from "./pages/SignupStep1";
import SignupStep2 from "./pages/SignupStep2";
import SignupStep3 from "./pages/SignupStep3";
import StartInvesting from "./pages/StartInvesting";
import StartSignup from "./pages/StartSignup";
import StockDetail from "./pages/StockDetail";
import StrategyComingSoon from "./pages/StrategyComingSoon";
import StrategyDetail from "./pages/StrategyDetail";
import StrategyF4List from "./pages/StrategyF4List";
import StrategyList from "./pages/StrategyList";
import StrategyPersonalizedPreview from "./pages/StrategyPersonalizedPreview";
import TransactionDetail from "./pages/TransactionDetail";
import TransactionHistory from "./pages/TransactionHistory";
import {
  toAccountOperationMode,
  toOperationMode,
  type OperationMode,
} from "./data/fees";
import {
  analyzeInvestorProfileApi,
  ApiError,
  applyLatestModelRecommendationsApi,
  createAdditionalInvestmentApi,
  createWithdrawalApi,
  getMyAccountApi,
    getStrategiesApi,
  sendEmailVerificationApi,
  selectStrategyApi,
  signupTermsApi,
  startInvestmentApi,
  verifyEmailVerificationApi,
  type SignupPayload,
  type StrategyRecommendationItemResponse,
  type StrategyResponse,
} from "./lib/backendApi";
import {
  buildInvestorAnswerPayload,
  mapInvestorProfileResponse,
} from "./lib/investorProfile";
import {
  resolveInvestmentEntryStep,
  resolvePreviousStep,
  type InvestmentEntryStep,
} from "./lib/investmentFlow";
import {
  createFeinHistoryState,
  fallbackScreen,
  hasFeinBackEntry,
  parseFeinHistoryState,
  pushScreenHistory,
  replaceScreenHistory,
  type ScreenHistoryContext,
} from "./lib/screenHistory";
import { resolvePortfolioStrategy } from "./lib/strategyCatalog";
import { useAuthStore } from "./store/authStore";
import { useInvestmentStore } from "./store/investmentStore";
import { useTradingStore } from "./store/tradingStore";
import type { Screen, SignupPersonal } from "./types";

/** 새로고침해도 유지할 최소한의 내비게이션 상태 — sessionStorage 에 저장한다(탭을 닫으면 사라짐).
 *  회원가입 입력값처럼 민감하거나 오래 들고 있을 필요 없는 값은 여기 포함하지 않는다.
 *  사용자별로 분리된 키가 아니라, 로그아웃 시 authStore.logout()/initialize() 이 이 키를 함께 지운다
 *  (같은 브라우저에서 다른 사용자가 로그인해도 이전 사용자의 화면 상태를 이어받지 않도록). */
const SESSION_KEY = "fein.session-nav";
interface PersistedNav {
  screen: Screen;
  strategyId: string;
  stockCode: string;
  stockBackTarget: Screen;
  selectedTransactionId: string;
  transactionBackTarget: Screen;
  rebalanceBackTarget: Screen;
  strategyDetailBackTarget: Screen;
  investmentMode: OperationMode;
  accountSetupMode: OperationMode;
  loginContext: LoginContext;
  postDiagnosisTarget: Screen;
  pendingStartAfterLogin: boolean;
  pendingReturnToStrategy: boolean;
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
 *  투자 시작 Flow(invest-*) 화면들도 로그인 이후에만 진입 가능한 흐름이라 함께 포함한다.
 *  'strategy'(Strategy Detail)와 'strategy-list'는 의도적으로 제외한다 — 비회원 접근 정책상 전략을
 *  읽고 기본 백테스트를 보는 것은 공개(PUBLIC)이고, 실제 조작/투자만 그 화면 내부에서 개별적으로
 *  로그인을 요구한다(handleStartInvesting/requestLoginForBacktest 참고). */
const PROTECTED_SCREENS: Screen[] = [
  "dashboard",
  "portfolio",
  "portfolio-detail",
  "account-setup",
  "account-deposit",
  "stock",
  "start",
  "transactions",
  "transaction-detail",
  "rebalance-alerts",
  "all-holdings",
  "invest-terms",
  "invest-account",
  "invest-deposit",
  "invest-confirm",
  "fund-add",
  "fund-add-confirm",
  "fund-add-pending",
  "fund-withdraw",
  "fund-withdraw-confirm",
  "fund-withdraw-pending",
];

/** 투자 시작 Flow(약관~최종확인) 화면 목록 — Header 등으로 이 밖으로 나가면 inFlight(새로고침 복원용 진행 상태)를 정리한다 */
const INVEST_FLOW_SCREENS: Screen[] = [
  "invest-terms",
  "invest-account",
  "invest-deposit",
  "invest-confirm",
];

/** 실제 전략 카탈로그 객체가 있어야 내용을 안전하게 렌더링할 수 있는 화면들. */
const STRATEGY_DATA_SCREENS: Screen[] = [
  "strategy",
  "start",
  "invest-terms",
  "invest-account",
  "invest-deposit",
  "invest-confirm",
  "dashboard",
  "portfolio-detail",
  "rebalance-alerts",
  "fund-add",
  "fund-add-confirm",
  "fund-withdraw",
  "fund-withdraw-confirm",
];

/** 실제 계좌의 selected_strategy_id를 Source of Truth로 써야 하는 포트폴리오 화면들. */
const PORTFOLIO_STRATEGY_SCREENS: Screen[] = [
  "dashboard",
  "portfolio-detail",
  "rebalance-alerts",
  "fund-add",
  "fund-add-confirm",
  "fund-withdraw",
  "fund-withdraw-confirm",
];

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
  const [screen, setScreenState] = useState<Screen>(
    persistedNav.screen ?? "home",
  );
  const [personal, setPersonal] = useState<SignupPersonal>({
    name: "",
    birthdate: "",
    email: "",
    agreements: { b: false, c: false, ai: false },
  });
  /** 회원가입 Step 02(이메일 인증) 진행 상태 — 화면 전환과 무관하게 App.tsx가 들고 있어야
   *  Step 02/03 사이를 오가도(뒤로가기) 인증 완료 상태가 유지된다. email이 바뀌면(Step 01 재수정)
   *  반드시 초기화한다 — 아래 handlePersonalChange 참고. */
  const [emailVerification, setEmailVerification] = useState<{
    email: string;
    verificationId: string;
    expiresInSeconds: number;
    resendAfterSeconds: number;
    token: string | null;
  } | null>(null);
  /** SignupStep1에 onChange로 넘기는 wrapper — value.email이 실제로 바뀐 순간에만 기존 이메일
   *  인증 상태를 reset한다(단순 리렌더/다른 필드 수정으로는 reset하지 않는다). */
  const handlePersonalChange = (next: SignupPersonal) => {
    if (emailVerification && next.email !== personal.email) {
      setEmailVerification(null);
    }
    setPersonal(next);
  };
  // 전략 선택은 실제 GET /strategies 카탈로그의 id 하나만 저장한다. 상세·투자 흐름에서 로컬 STRATEGIES
  // 목업으로 되돌아가지 않도록 이름과 위험도 등 화면 데이터도 같은 실 카탈로그에서 파생한다.
  const [strategyId, setStrategyId] = useState<string>(
    persistedNav.strategyId ?? "low",
  );
  const [strategyCatalog, setStrategyCatalog] = useState<StrategyResponse[]>(
    [],
  );
  const [isStrategyCatalogLoading, setIsStrategyCatalogLoading] =
    useState(true);
  const [strategyCatalogError, setStrategyCatalogError] = useState<
    string | null
  >(null);
  const [strategyCatalogRetry, setStrategyCatalogRetry] = useState(0);
  const [strategyRecommendation, setStrategyRecommendation] =
    useState<StrategyRecommendationItemResponse | null>(null);
  const [strategyDetailBackTarget, setStrategyDetailBackTarget] =
    useState<Screen>(persistedNav.strategyDetailBackTarget ?? "strategy-list");
  // 추가 투자/출금 STEP 1(금액) → STEP 2(확인) 사이에서만 쓰는 draft 금액 — 새로고침 유지가 필요 없는
  // 일회성 입력값이라 persistedNav(sessionStorage)에는 넣지 않는다.
  const [fundAddAmount, setFundAddAmount] = useState(0);
  const [fundWithdrawAmount, setFundWithdrawAmount] = useState(0);
  const [fundOperation, setFundOperation] = useState<
    import("./lib/backendApi").FundOperationResponse | null
  >(null);
  const [fundOperationError, setFundOperationError] = useState<string | null>(
    null,
  );
  const [fundOperationIdempotencyKey, setFundOperationIdempotencyKey] =
    useState<string | null>(null);
  const [isFundOperationSubmitting, setIsFundOperationSubmitting] =
    useState(false);

  const strategy =
    strategyCatalog.find((item) => item.id === strategyId) ?? null;
  useEffect(() => {
    if (!STRATEGY_DATA_SCREENS.includes(screen)) {
      setIsStrategyCatalogLoading(false);
      return;
    }
    if (strategyCatalog.length > 0) {
      setIsStrategyCatalogLoading(false);
      return;
    }
    let cancelled = false;
    setIsStrategyCatalogLoading(true);
    setStrategyCatalogError(null);
    getStrategiesApi()
      .then((items) => {
        if (cancelled) return;
        if (items.length === 0) {
          setStrategyCatalogError("현재 이용 가능한 전략이 없어요.");
        } else {
          setStrategyCatalog(items);
        }
        setIsStrategyCatalogLoading(false);
      })
      .catch((error) => {
        if (!cancelled) {
          setStrategyCatalogError(
            error instanceof Error
              ? error.message
              : "전략 목록을 불러오지 못했어요.",
          );
          setIsStrategyCatalogLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [screen, strategyCatalog.length, strategyCatalogRetry]);
  const [stockCode, setStockCode] = useState(
    persistedNav.stockCode ?? "005930",
  );
  // 종목 상세 진입 지점에 따라 뒤로가기 목적지가 달라진다 (start 에서 왔으면 start로, portfolio 에서 왔으면 portfolio-detail로)
  const [stockBackTarget, setStockBackTarget] = useState<Screen>(
    persistedNav.stockBackTarget ?? "portfolio-detail",
  );
  // 거래 상세 진입 지점(포트폴리오 상세의 "최근 거래" 3건 vs 전체 거래 내역)에 따라 뒤로가기 목적지가 달라진다.
  const [selectedTransactionId, setSelectedTransactionId] = useState(
    persistedNav.selectedTransactionId ?? "",
  );
  const [transactionBackTarget, setTransactionBackTarget] = useState<Screen>(
    persistedNav.transactionBackTarget ?? "portfolio-detail",
  );
  // 리밸런싱 제안 상세 진입 지점(Portfolio/PortfolioAuto 요약 위젯 vs PortfolioDetail의 같은 위젯)에
  // 따라 뒤로가기 목적지가 달라진다 — portfolio-detail로 고정해두면 Portfolio에서 들어온 유저가
  // "돌아가기"를 눌렀을 때 원래 없던 PortfolioDetail을 거치게 된다.
  const [rebalanceBackTarget, setRebalanceBackTarget] = useState<Screen>(
    persistedNav.rebalanceBackTarget ?? "portfolio-detail",
  );
  // 투자자 정보 확인(risk) 완료 후 어디로 이어갈지 + 진입 맥락(안내 문구)
  const [postDiagnosisTarget, setPostDiagnosisTarget] =
    useState<Screen>(persistedNav.postDiagnosisTarget ?? "risk-result");
  const [riskNotice, setRiskNotice] = useState<string | undefined>(undefined);
  const [riskErrorCode, setRiskErrorCode] = useState<string | null>(null);
  // 온보딩 흐름에서 RiskResult를 skip하고 곧장 StrategyList로 넘어온 직후에만 true — StrategyList가
  // 상단에 짧은 안내 문구를 보여줄지 판단하는 용도. strategy-list를 벗어나면 아래 effect가 초기화한다.
  const [justFinishedInvestorProfile, setJustFinishedInvestorProfile] =
    useState(false);
  // 투자자 정보 확인(risk) 완료 버튼을 누른 뒤 백엔드 분석 응답을 기다리는 동안 true — 이 결과가
  // RiskResult/재로그인 복원의 Source of Truth이므로, 응답이 오기 전까지는 화면을 넘기지 않는다.
  const [isDiagnosisSubmitting, setIsDiagnosisSubmitting] = useState(false);
  // 비회원이 Strategy Detail "이 전략으로 시작하기"를 눌러 로그인 화면으로 보내진 경우 true —
  // 로그인 완료 후 Portfolio가 아니라 원래 하려던 투자 시작 절차로 이어간다(아래 Login onLogin 참고).
  const [pendingStartAfterLogin, setPendingStartAfterLogin] = useState(
    persistedNav.pendingStartAfterLogin ?? false,
  );
  // 비회원이 백테스트 잠긴 기간(Inline Login CTA)에서 로그인 화면으로 보내진 경우 true — 로그인 후
  // Portfolio가 아니라 보고 있던 Strategy Detail로만 복귀시킨다(그 기간을 자동 실행하지는 않는다).
  const [pendingReturnToStrategy, setPendingReturnToStrategy] = useState(
    persistedNav.pendingReturnToStrategy ?? false,
  );
  // 로그인 화면 title/subtitle을 결정하는 진입 경로 — Header의 일반 로그인은 기본값(header)을 쓰고,
  // Home/Strategy Detail의 특정 CTA는 각자 진입 시점에 이 값을 명시적으로 세팅한다.
  const [loginContext, setLoginContext] = useState<LoginContext>(
    persistedNav.loginContext ?? "header",
  );
  // 투자 시작 Flow(약관 → 계좌 준비 → 입금 → 최종 확인) 동안 유지해야 하는 선택 금액/운용방식
  // 기본값은 "자동으로 운용" — 처음 투자하는 사용자에게 이 방식을 우선 추천하는 정책
  const [investmentAmount, setInvestmentAmount] = useState(1_000_000);
  const [investmentMode, setInvestmentMode] = useState<OperationMode>(
    persistedNav.investmentMode ?? "auto",
  );
  const [accountSetupMode, setAccountSetupMode] =
    useState<OperationMode>(persistedNav.accountSetupMode ?? "manual");
  const [investmentAgreements, setInvestmentAgreements] = useState<
    SignupPayload["agreements"]
  >([]);
  const register = useAuthStore((s) => s.register);
  const initialize = useAuthStore((s) => s.initialize);
  const authenticatedUser = useAuthStore((s) => s.user);
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);
  const isHydrating = useAuthStore((s) => s.isHydrating);
  const hydrateInvestorProfile = useAuthStore(
    (s) => s.hydrateInvestorProfile,
  );
  const completeInvestorProfile = useAuthStore(
    (s) => s.completeInvestorProfile,
  );
  const accessToken = useAuthStore((s) => s.accessToken);
  const ensureAccount = useTradingStore((s) => s.ensureAccount);
  const prepareAccount = useTradingStore((s) => s.prepareAccount);
  const depositCash = useTradingStore((s) => s.depositCash);
  const tradingAccount = useTradingStore((s) => s.account);
  const portfolioStrategy = resolvePortfolioStrategy(
    strategyCatalog,
    strategy,
    tradingAccount ? tradingAccount.selected_strategy_id : undefined,
  );
  const screenStrategy = PORTFOLIO_STRATEGY_SCREENS.includes(screen)
    ? portfolioStrategy
    : strategy;
  const termsAcceptedStrategyIds = useInvestmentStore(
    (s) => s.termsAcceptedStrategyIds,
  );
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
  const clearPendingInvestment = useInvestmentStore(
    (s) => s.clearPendingInvestment,
  );
  const hydrateForUser = useInvestmentStore((s) => s.hydrateForUser);
  const setInFlightStep = useInvestmentStore((s) => s.setInFlightStep);
  const clearInFlight = useInvestmentStore((s) => s.clearInFlight);
  const setActiveMode = useInvestmentStore((s) => s.setActiveMode);
  const markActiveModeChecked = useInvestmentStore(
    (s) => s.markActiveModeChecked,
  );
  const setAccountActiveStrategy = useInvestmentStore(
    (s) => s.setAccountActiveStrategy,
  );

  const buildHistoryContext = (
    overrides: ScreenHistoryContext = {},
  ): ScreenHistoryContext => ({
    strategyId,
    strategyDetailBackTarget,
    stockCode,
    stockBackTarget,
    selectedTransactionId,
    transactionBackTarget,
    rebalanceBackTarget,
    investmentMode,
    accountSetupMode,
    loginContext,
    postDiagnosisTarget,
    pendingStartAfterLogin,
    pendingReturnToStrategy,
    ...overrides,
  });

  const applyHistoryContext = (context: ScreenHistoryContext) => {
    if (context.strategyId !== undefined) setStrategyId(context.strategyId);
    if (context.strategyDetailBackTarget !== undefined) {
      setStrategyDetailBackTarget(context.strategyDetailBackTarget);
    }
    if (context.stockCode !== undefined) setStockCode(context.stockCode);
    if (context.stockBackTarget !== undefined) {
      setStockBackTarget(context.stockBackTarget);
    }
    if (context.selectedTransactionId !== undefined) {
      setSelectedTransactionId(context.selectedTransactionId);
    }
    if (context.transactionBackTarget !== undefined) {
      setTransactionBackTarget(context.transactionBackTarget);
    }
    if (context.rebalanceBackTarget !== undefined) {
      setRebalanceBackTarget(context.rebalanceBackTarget);
    }
    if (context.investmentMode !== undefined) {
      setInvestmentMode(context.investmentMode);
    }
    if (context.accountSetupMode !== undefined) {
      setAccountSetupMode(context.accountSetupMode);
    }
    if (context.loginContext !== undefined) {
      setLoginContext(context.loginContext);
    }
    if (context.postDiagnosisTarget !== undefined) {
      setPostDiagnosisTarget(context.postDiagnosisTarget);
    }
    if (context.pendingStartAfterLogin !== undefined) {
      setPendingStartAfterLogin(context.pendingStartAfterLogin);
    }
    if (context.pendingReturnToStrategy !== undefined) {
      setPendingReturnToStrategy(context.pendingReturnToStrategy);
    }
  };

  /** 사용자 주도 화면 이동은 항상 새 브라우저 history entry를 만든다. */
  const pushScreen = (
    target: Screen,
    contextOverrides: ScreenHistoryContext = {},
  ) => {
    // 현재 entry의 화면과 보조 상태를 먼저 최신 React state로 보정해야 Back으로 돌아왔을 때
    // 상세 대상이나 진입 화면이 다른 최신 값으로 덮이지 않는다.
    const nextContext = buildHistoryContext(contextOverrides);
    pushScreenHistory(
      window.history,
      screen,
      buildHistoryContext(),
      target,
      nextContext,
    );
    applyHistoryContext(nextContext);
    setScreenState(target);
  };

  /** 완료·인증 가드·잘못된 복원처럼 이전 화면을 다시 노출하면 안 되는 전환에 사용한다. */
  const replaceScreen = (
    target: Screen,
    contextOverrides: ScreenHistoryContext = {},
  ) => {
    const nextContext = buildHistoryContext(contextOverrides);
    replaceScreenHistory(window.history, target, nextContext);
    applyHistoryContext(nextContext);
    setScreenState(target);
  };

  /** 앱이 만든 이전 entry가 없을 때만 화면별 안전한 fallback으로 현재 entry를 교체한다. */
  const goBackOrTo = (fallback: Screen = fallbackScreen(screen)) => {
    if (hasFeinBackEntry(window.history)) {
      window.history.back();
    } else {
      replaceScreen(fallback);
    }
  };

  /**
   * invest-terms~invest-confirm 중 한 화면으로 이동할 때 항상 이 함수를 거친다.
   * strategyId/금액/운용방식을 항상 함께 동기화해서 화면에 보이는 값과 새로고침 복원용
   * inFlight 기록이 어긋나지 않게 한다(호출부마다 따로 setStrategyId 등을 챙길 필요 없음).
   *
   * step이 invest-deposit/invest-confirm이면 — 즉 계좌 준비가 끝나 남은 건 입금·최종 확인뿐이면 —
   * pendingInvestment를 함께 기록한다. "나중에 입금할게요" 버튼을 눌렀는지와 무관하게, 계좌 준비가
   * 끝난 시점부터 DEPOSIT_PENDING으로 간주해야 Home/다른 메뉴로 이탈하거나 로그아웃해도 다시
   * 돌아왔을 때 입금 단계부터 이어갈 수 있다. 실제 투자 시작(InvestConfirm 성공) 시에만 clear한다.
   */
  const enterInvestmentStep = (
    step: InvestmentEntryStep,
    ctxStrategyId: string,
    ctxAmount: number,
    ctxMode: OperationMode,
    agreements: SignupPayload["agreements"] = investmentAgreements,
    historyMode: "push" | "replace" = "push",
  ) => {
    setStrategyId(ctxStrategyId);
    setInvestmentAmount(ctxAmount);
    setInvestmentMode(ctxMode);
    setInFlightStep({
      step,
      strategyId: ctxStrategyId,
      amount: ctxAmount,
      mode: ctxMode,
      agreements,
    });
    if (step === "invest-deposit" || step === "invest-confirm") {
      const ctxStrategyName =
        strategyCatalog.find((item) => item.id === ctxStrategyId)?.name ??
        ctxStrategyId;
      deferDeposit({
        strategyId: ctxStrategyId,
        strategyName: ctxStrategyName,
        amount: ctxAmount,
        mode: ctxMode,
      });
    }
    const move = historyMode === "replace" ? replaceScreen : pushScreen;
    move(step, {
      strategyId: ctxStrategyId,
      investmentMode: ctxMode,
    });
  };

  /**
   * StartInvesting "이대로 시작하기" — 이미 완료한 단계는 건너뛰고 다음 필요한 단계로 이동한다.
   * 방금 고른 mode가 지금까지의 investmentMode와 다를 수 있으므로(운용방식 전환 시도), 클로저의
   * sesacAccount(현재 investmentMode 기준)를 그대로 쓰면 안 되고 mode에 맞는 계좌를 다시 찾아야 한다.
   */
  const enterInvestmentFlow = (amount: number, mode: OperationMode) => {
    const accountForMode = accountsByMode[mode] ?? null;
    const step = resolveInvestmentEntryStep({
      strategyId,
      amount,
      termsAcceptedStrategyIds,
      sesacAccount: accountForMode,
    });
    enterInvestmentStep(step, strategyId, amount, mode);
  };

  /**
   * 투자 Flow 화면들의 "이전으로" — 고정된 이전 화면이 아니라, 현재 상태 기준으로 아직 필요한
   * 가장 가까운 이전 단계로 돌아간다. 더 돌아갈 단계가 없으면(이미 완료된 상태로 이 화면에
   * 들어온 경우) 금액 선택 화면('start')으로 나가고, 그 시점에 inFlight도 정리한다.
   */
  const goBackInInvestmentFlow = (currentStep: InvestmentEntryStep) => {
    const prev = resolvePreviousStep(currentStep, {
      strategyId,
      amount: investmentAmount,
      termsAcceptedStrategyIds,
      sesacAccount,
    });
    if (prev === "start") {
      clearInFlight();
      goBackOrTo("start");
    } else {
      setInFlightStep({
        step: prev,
        strategyId,
        amount: investmentAmount,
        mode: investmentMode,
        agreements: investmentAgreements,
      });
      goBackOrTo(prev);
    }
  };

  /**
   * Header "나의 포트폴리오"/로그인 성공 등 Portfolio로 향하는 모든 경로가 거치는 관문.
   * DEPOSIT_PENDING(계좌는 연결됐지만 아직 투자가 시작되지 않은) 상태라면 Portfolio 대신 입금 요청
   * 화면으로 보낸다. 투자 Flow 화면에서 그 밖의 목적지(인사이트/투자전략 등)로 명시적으로 이동할 때는
   * inFlight(새로고침 복원용 진행 상태)만 정리한다 — pendingInvestment는 실제 투자가 시작되기 전까지
   * 별도로 유지된다(enterInvestmentStep 참고).
   *
   * 로그인 직후에는 Login.tsx가 login() 완료와 동시에 이 함수를 동기적으로 호출하는데, 이 시점엔
   * "사용자별 hydrate" useEffect가 아직 커밋되지 않았을 수 있다(리액트 이펙트는 렌더 이후 실행).
   * 그래서 반응형 클로저 값(pendingInvestment/accountsByMode/termsAcceptedStrategyIds)을 믿는 대신,
   * 여기서 현재 로그인된 사용자 기준으로 강제로 다시 hydrate한 뒤 스토어에서 바로 최신 값을 읽는다.
   *
   * DEPOSIT_PENDING 복귀 화면은 'invest-deposit'으로 고정하지 않는다 — pendingInvestment가 남아있어도
   * 그 사이 다른 경로로 이미 입금이 끝나 잔액이 충분해졌을 수 있어(예: "이 전략으로 시작하기"를 다시
   * 눌러 곧장 입금까지 마친 경우), resolveInvestmentEntryStep으로 현재 계좌 잔액 기준 필요한 단계를
   * 다시 계산한다 — 잔액이 이미 충분하면 "0원 입금하기"가 뜨는 invest-deposit 대신 invest-confirm 등
   * 실제로 필요한 단계로 보낸다.
   */
  const navigate = (
    target: Screen,
    options: {
      replace?: boolean;
      context?: ScreenHistoryContext;
    } = {},
  ) => {
    let navigationContext = options.context;
    // 이 함수를 거쳐 로그인으로 가는 경로(Header 일반 로그인, "나의 포트폴리오" 등 guarded 메뉴 리다이렉트)는
    // 모두 기본 context — Strategy Detail의 특정 CTA는 이 함수를 거치지 않고 각자
    // requestLoginForBacktest/handleStartInvesting에서 직접 context를 세팅한다.
    if (target === "login") {
      setLoginContext("header");
      navigationContext = { ...navigationContext, loginContext: "header" };
    }
    if (target === "portfolio") {
      const userId = useAuthStore.getState().user?.user_id ?? null;
      hydrateForUser(userId);
      const freshState = useInvestmentStore.getState();
      const pending = freshState.pendingInvestment;
      if (pending) {
        const accountForPendingMode =
          freshState.accountsByMode[pending.mode] ?? null;
        const step = resolveInvestmentEntryStep({
          strategyId: pending.strategyId,
          amount: pending.amount,
          termsAcceptedStrategyIds: freshState.termsAcceptedStrategyIds,
          sesacAccount: accountForPendingMode,
        });
        enterInvestmentStep(
          step,
          pending.strategyId,
          pending.amount,
          pending.mode,
          investmentAgreements,
          options.replace ? "replace" : "push",
        );
        return;
      }
    }
    if (
      INVEST_FLOW_SCREENS.includes(screen) &&
      !INVEST_FLOW_SCREENS.includes(target)
    ) {
      clearInFlight();
    }
    const move = options.replace ? replaceScreen : pushScreen;
    move(target, navigationContext);
  };

  const userName = authenticatedUser?.name ?? (personal.name.trim() || "서연");

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
          setInvestmentAmount(restored.amount);
          setInvestmentAgreements(restored.agreements ?? []);
          replaceScreen(restored.step, {
            strategyId: restored.strategyId,
            investmentMode: restored.mode,
          });
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
      replaceScreen("home", {
        strategyId: "low",
        strategyDetailBackTarget: "strategy-list",
        stockCode: "005930",
        stockBackTarget: "portfolio-detail",
        selectedTransactionId: "",
        transactionBackTarget: "portfolio-detail",
        rebalanceBackTarget: "portfolio-detail",
        investmentMode: "auto",
        accountSetupMode: "manual",
        loginContext: "header",
        postDiagnosisTarget: "risk-result",
        pendingStartAfterLogin: false,
        pendingReturnToStrategy: false,
      });
    }
    prevUserIdRef.current = currentUserId;
  }, [authenticatedUser?.user_id, hydrateForUser]);

  // activeMode는 이 브라우저에서 투자 시작/전략 변경을 실제로 거친 세션에만 로컬로 남는다. 새
  // 브라우저나 localStorage가 초기화된 환경에서는 실제로는 이미 투자 중이어도 activeMode를 알 수
  // 없어 Portfolio 화면 분기(자동/반자동)나 Strategy Detail CTA가 "미투자"로 잘못 판단한다. 그래서
  // 로그인 후 로컬에 activeMode가 없으면 두 운용방식 계좌를 함께 조회해 이미 선택된 전략이 있는
  // 계좌를 찾으면 그 운용방식으로 activeMode를 맞춰준다.
  //
  // 두 운용방식 모두 selected_strategy_id가 있는(동시에 활성인) 경우는 프론트만으로는 어느 쪽이
  // "지금" 실제로 쓰이고 있는지 구분할 근거가 없다 — 백엔드에 마지막 활성 운용방식을 기록/복원하는
  // 필드가 없어 조회 순서로 결정할 수밖에 없는데, 그건 임의적이라 근본 해결이 아니다. 이 프론트만의
  // 범위에서는 이미 다른 화면들이 쓰는 것과 같은 기본값(반자동)으로 수렴시켜 최소한 일관되게라도
  // 동작하게 해두고, 완전한 해결은 백엔드에 "마지막 활성 운용방식" 같은 필드가 추가돼야 한다.
  useEffect(() => {
    if (!accessToken || activeMode !== null) return;
    let cancelled = false;
    (async () => {
      const [semiAuto, auto] = await Promise.all(
        (["SEMI_AUTO", "AUTO"] as const).map((probeMode) =>
          getMyAccountApi(accessToken, probeMode).catch(() => null),
        ),
      );
      if (cancelled) return;
      const semiAutoActive = Boolean(semiAuto?.selected_strategy_id);
      const autoActive = Boolean(auto?.selected_strategy_id);
      if (semiAutoActive && !autoActive) {
        setActiveMode("manual");
      } else if (autoActive && !semiAutoActive) {
        setActiveMode("auto");
      } else if (semiAutoActive && autoActive) {
        setActiveMode("manual"); // 위 주석 참고 — 둘 다 활성이면 기존 앱 기본값(반자동)으로 수렴
      } else if (semiAuto && !auto) {
        setActiveMode("manual");
      } else if (auto && !semiAuto) {
        setActiveMode("auto");
      } else if (semiAuto && auto) {
        setActiveMode("manual");
      } else {
        markActiveModeChecked();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken, activeMode, setActiveMode, markActiveModeChecked]);

  // 새로고침해도 같은 화면에 남아있도록 내비게이션 상태를 sessionStorage 에 계속 동기화한다.
  useEffect(() => {
    const nav: PersistedNav = {
      screen,
      strategyId,
      stockCode,
      stockBackTarget,
      selectedTransactionId,
      transactionBackTarget,
      rebalanceBackTarget,
      strategyDetailBackTarget,
      investmentMode,
      accountSetupMode,
      loginContext,
      postDiagnosisTarget,
      pendingStartAfterLogin,
      pendingReturnToStrategy,
    };
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(nav));
  }, [
    screen,
    strategyId,
    stockCode,
    stockBackTarget,
    selectedTransactionId,
    transactionBackTarget,
    rebalanceBackTarget,
    strategyDetailBackTarget,
    investmentMode,
    accountSetupMode,
    loginContext,
    postDiagnosisTarget,
    pendingStartAfterLogin,
    pendingReturnToStrategy,
  ]);

  // 같은 화면 안에서 전략·종목 같은 복원 context가 바뀌어도 현재 history entry를 최신화한다.
  // entry를 추가하지 않으므로 Back/Forward 순서에는 영향을 주지 않는다.
  useEffect(() => {
    const current = parseFeinHistoryState(window.history.state);
    if (!current || current.screen !== screen) return;
    window.history.replaceState(
      createFeinHistoryState(screen, current.depth, buildHistoryContext()),
      "",
    );
  }, [
    screen,
    strategyId,
    strategyDetailBackTarget,
    stockCode,
    stockBackTarget,
    selectedTransactionId,
    transactionBackTarget,
    rebalanceBackTarget,
    investmentMode,
    accountSetupMode,
    loginContext,
    postDiagnosisTarget,
    pendingStartAfterLogin,
    pendingReturnToStrategy,
  ]);

  // 앱 최초 마운트 시(새로고침 포함) 현재 entry에 전체 화면 복원 정보를 기록한다.
  useEffect(() => {
    const existing = parseFeinHistoryState(window.history.state);
    window.history.replaceState(
      createFeinHistoryState(
        screen,
        existing?.depth ?? 0,
        buildHistoryContext(),
      ),
      "",
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Back/Forward에서는 새 entry를 만들지 않고 해당 entry의 화면과 상세 context만 복원한다.
  useEffect(() => {
    const handlePopState = (event: PopStateEvent) => {
      const state = parseFeinHistoryState(event.state);
      if (!state) return;
      if (
        PROTECTED_SCREENS.includes(state.screen) &&
        !useAuthStore.getState().isLoggedIn
      ) {
        window.history.replaceState(
          createFeinHistoryState("login", state.depth, state.context),
          "",
        );
        applyHistoryContext(state.context);
        setScreenState("login");
        return;
      }
      applyHistoryContext(state.context);
      setScreenState(state.screen);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // react-router 없이 screen state 하나로 화면을 전환하는 구조라, 브라우저가 자동으로 해주는
  // 스크롤 리셋이 없다 — 스크롤을 많이 내린 화면(예: PortfolioDetail)에서 다른 화면(예: StockDetail)으로
  // 넘어가면 새 화면이 이전 스크롤 위치 그대로 렌더링되어 sticky Header가 화면 중간에 끼어 보인다.
  // strategyId/stockCode 등 같은 화면 안에서 바뀌는 값에는 반응하지 않도록 screen만 의존성으로 둔다.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [screen]);

  // 로그인이 필요한 화면을 새로고침으로 복원했는데, 토큰 검증(initialize)이 끝난 뒤
  // 실제로는 로그인 상태가 아닌 것으로 확인되면(토큰 만료 등) 로그인 화면으로 돌려보낸다.
  useEffect(() => {
    if (!isHydrating && !isLoggedIn && PROTECTED_SCREENS.includes(screen)) {
      replaceScreen("login");
    }
  }, [isHydrating, isLoggedIn, screen]);

  // 거래 상세를 새로고침으로 복원했는데 selectedTransactionId 를 복원할 수 없으면(예: 이 필드가 없던
  // 이전 버전의 sessionStorage) "거래 내역을 찾을 수 없어요" 대신 전체 거래 내역으로 보낸다.
  useEffect(() => {
    if (screen === "transaction-detail" && !selectedTransactionId) {
      replaceScreen("transactions");
    }
  }, [screen, selectedTransactionId]);

  // 추가 투자/출금 확인 화면(screen)은 sessionStorage로 복원되지만 금액(fundAddAmount/
  // fundWithdrawAmount)은 새로고침 유지가 필요 없는 일반 state라 복원되지 않는다(0으로 초기화됨).
  // 그대로 두면 확인 화면이 0원인 채로 뜨고 실행 버튼이 금액을 재검증하지 않아 다음 단계로 넘어갈 수
  // 있어, 금액을 복원할 수 없는 채로 확인 화면을 새로고침한 경우 STEP 1(금액 입력)으로 돌려보낸다.
  useEffect(() => {
    if (screen === "fund-add-confirm" && fundAddAmount <= 0) {
      replaceScreen("fund-add");
    }
  }, [screen, fundAddAmount]);
  useEffect(() => {
    if (screen === "fund-withdraw-confirm" && fundWithdrawAmount <= 0) {
      replaceScreen("fund-withdraw");
    }
  }, [screen, fundWithdrawAmount]);

  // 성공 결과 데이터는 일회성 React state이므로 pending 화면을 새로고침하면 안전한 화면으로 돌아간다.
  useEffect(() => {
    if (
      (screen === "fund-add-pending" || screen === "fund-withdraw-pending") &&
      !fundOperation
    ) {
      replaceScreen("portfolio");
    }
  }, [screen, fundOperation]);

  // strategy-list를 벗어나면 온보딩 직후 안내 문구를 리셋한다 — Header "투자전략"으로 다시
  // 들어왔을 때는 온보딩 완료 안내가 다시 보이면 안 된다.
  useEffect(() => {
    if (screen !== "strategy-list" && justFinishedInvestorProfile) {
      setJustFinishedInvestorProfile(false);
    }
  }, [screen, justFinishedInvestorProfile]);

  /** risk 화면 진입 지점 — 완료 후 목적지와 안내 문구를 함께 정한다 */
  const startInvestorProfile = (
    target: Screen,
    opts?: { notice?: string },
    historyMode: "push" | "replace" = "push",
    contextOverrides: ScreenHistoryContext = {},
  ) => {
    setPostDiagnosisTarget(target);
    setRiskNotice(opts?.notice);
    setRiskErrorCode(null);
    const move = historyMode === "replace" ? replaceScreen : pushScreen;
    move("risk", { ...contextOverrides, postDiagnosisTarget: target });
  };

  /**
   * investorProfileCompleted 분기만 담당 — 로그인은 이미 됐다고 가정한다.
   * getState()로 최신값을 직접 읽는 이유: 로그인 직후 onLogin 콜백에서도 이 로직을 그대로 타는데,
   * 그 시점엔 아직 리렌더가 안 끝나 이 컴포넌트의 investorProfileCompleted 클로저가 낡은 값일 수 있다.
   */
  const proceedToStartInvesting = async (
    historyMode: "push" | "replace" = "push",
    contextOverrides: ScreenHistoryContext = {},
  ) => {
    // 로그인 직후/새로고침 직후의 fire-and-forget hydration이 끝나기 전에는
    // investorProfileCompleted=false를 미진단으로 해석하지 않는다.
    await hydrateInvestorProfile();
    const latestAuth = useAuthStore.getState();
    if (latestAuth.investorProfileCompleted) {
      const move = historyMode === "replace" ? replaceScreen : pushScreen;
      move("investor-check", contextOverrides);
    } else {
      startInvestorProfile(
        "start",
        {
          notice: "투자를 시작하기 전에 투자자 정보를 확인해주세요.",
        },
        historyMode,
        contextOverrides,
      );
    }
  };

  /**
   * StrategyDetail "이 전략으로 시작하기" — 실제 투자 실행의 시작점이라 로그인이 먼저 필요하다.
   * 비회원이면 로그인 화면으로 보내고, 로그인 완료 후 Portfolio가 아니라 여기로 다시 이어가도록
   * pendingStartAfterLogin을 세워둔다(strategyId는 이미 상태로 유지되고 있어 따로 안 챙겨도 된다).
   */
  const handleStartInvesting = () => {
    if (!isLoggedIn) {
      setLoginContext("strategy");
      setPendingStartAfterLogin(true);
      pushScreen("login", {
        loginContext: "strategy",
        pendingStartAfterLogin: true,
        pendingReturnToStrategy: false,
      });
      return;
    }
    void proceedToStartInvesting();
  };

  /**
   * Strategy Detail 백테스트의 잠긴 기간/직접 설정(Inline Login CTA)에서 로그인 화면으로 보내진 경우 —
   * 로그인 완료 후 Portfolio가 아니라 보고 있던 Strategy Detail로만 복귀한다(그 기간을 자동 실행하지는
   * 않는다). strategyId는 이미 상태로 유지되고 있어 따로 안 챙겨도 된다.
   */
  const requestLoginForBacktest = () => {
    setLoginContext("strategy");
    setPendingReturnToStrategy(true);
    pushScreen("login", {
      loginContext: "strategy",
      pendingStartAfterLogin: false,
      pendingReturnToStrategy: true,
    });
  };

  /**
   * Strategy Detail "이 전략으로 변경하기" 확인 — InvestConfirm과 동일하게 실제 계좌 API
   * (ensureAccount 내부에서 selected_strategy_id가 다르면 selectStrategyApi 호출)를 거친 뒤에만
   * 로컬 activeStrategyId를 갱신한다. 로컬 state만 바꾸고 끝내면 새로고침/Portfolio 재조회 시
   * 실제 계좌의 전략으로 되돌아가 화면과 어긋날 수 있어, 반드시 API 성공을 먼저 확인한다.
   *
   * 로컬 activeMode가 비어있어도(새 브라우저 등) StrategyDetail이 실제 계좌(tradingStore.account)
   * 기준으로 'change' CTA를 보여줄 수 있다 — 그 경우를 위해 activeMode가 없으면 이미 조회된 실제
   * 계좌의 operation_mode로 대신 판단하고, 성공하면 로컬 activeMode도 함께 맞춰준다.
   */
  const confirmStrategyChange = async () => {
    const realAccount = useTradingStore.getState().account;
    const mode =
      activeMode ??
      (realAccount ? toOperationMode(realAccount.operation_mode) : null);
    if (!accessToken || !mode) {
      throw new Error("로그인이 필요합니다.");
    }
    await ensureAccount(accessToken, strategyId, toAccountOperationMode(mode));
    setAccountActiveStrategy(mode, strategyId);
    setActiveMode(mode);
    navigate("portfolio", { replace: true });
  };

  const prepareStandaloneAccount = async (mode: OperationMode) => {
    if (!accessToken) throw new Error("로그인이 필요합니다.");
    setAccountSetupMode(mode);
    setActiveMode(mode);
    await prepareAccount(accessToken, toAccountOperationMode(mode));
    pushScreen("account-deposit", { accountSetupMode: mode });
  };

  const depositStandaloneCash = async (
    amount: number,
    idempotencyKey: string,
  ) => {
    if (!accessToken || !tradingAccount) {
      throw new Error("입금할 계좌를 확인할 수 없습니다.");
    }
    await depositCash(
      accessToken,
      tradingAccount.id,
      amount,
      idempotencyKey,
    );
    replaceScreen("portfolio");
  };

  return (
    <div className="min-h-screen bg-canvas">
      {screen === "home" && (
        <Home
          userName={userName}
          onNavigate={navigate}
        />
      )}

      {screen === "login" && (
        <Login
          context={loginContext}
          // 로그인 성공 — "이 전략으로 시작하기"를 거쳐 왔으면 그 절차로 이어가고, 잠긴 백테스트에서
          // 왔으면 보고 있던 Strategy Detail로 복귀하며, 그 외에는 헤더 "나의 포트폴리오"와 동일한
          // 목적지(Portfolio)로 이동. 회원가입 유도는 이제 Home "시작하기"/"내 투자성향 알아보기"가
          // 로그인을 거치지 않고 곧장 start-signup으로 보내므로 여기서 다룰 필요가 없다.
          onLogin={async () => {
            if (pendingStartAfterLogin) {
              setPendingStartAfterLogin(false);
              await proceedToStartInvesting("replace", {
                pendingStartAfterLogin: false,
                pendingReturnToStrategy: false,
              });
              return;
            }
            if (pendingReturnToStrategy) {
              setPendingReturnToStrategy(false);
              replaceScreen("strategy", {
                pendingReturnToStrategy: false,
              });
              return;
            }
            navigate("portfolio", {
              replace: true,
              context: {
                pendingStartAfterLogin: false,
                pendingReturnToStrategy: false,
              },
            });
          }}
          onSignup={() => {
            setPendingStartAfterLogin(false);
            setPendingReturnToStrategy(false);
            pushScreen("signup-1", {
              pendingStartAfterLogin: false,
              pendingReturnToStrategy: false,
            });
          }}
          onHome={() => {
            setPendingStartAfterLogin(false);
            setPendingReturnToStrategy(false);
            goBackOrTo("home");
          }}
          onNavigate={(s) => {
            setPendingStartAfterLogin(false);
            setPendingReturnToStrategy(false);
            navigate(s);
          }}
        />
      )}

      {screen === "start-signup" && (
        <StartSignup
          onNavigate={navigate}
          // 이메일만 SignupPersonal에 미리 채우고 기존 signup-1로 넘긴다 — 새 API/스키마 없음.
          // handlePersonalChange를 그대로 써서 email이 바뀌면 기존 emailVerification 리셋 로직도
          // 똑같이 적용된다.
          onContinue={(email) => {
            handlePersonalChange({ ...personal, email });
            pushScreen("signup-1");
          }}
        />
      )}

      {screen === "signup-1" && (
        <SignupStep1
          value={personal}
          onChange={handlePersonalChange}
          // 이메일로 인증번호 발송 성공 시에만 Step 02로 이동 — 실패하면 여기서 throw해 Step1이 에러를 보여준다.
          onRequestEmailVerification={async (email) => {
            const result = await sendEmailVerificationApi(email);
            setEmailVerification({
              email,
              verificationId: result.verification_id,
              expiresInSeconds: result.expires_in_seconds,
              resendAfterSeconds: result.resend_after_seconds,
              token: null,
            });
            pushScreen("signup-2");
          }}
          userName={userName}
          onNavigate={navigate}
        />
      )}
      {screen === "signup-2" && (
        <SignupStep2
          email={emailVerification?.email ?? personal.email}
          verified={emailVerification?.token != null}
          expiresInSeconds={emailVerification?.expiresInSeconds ?? 300}
          resendAfterSeconds={emailVerification?.resendAfterSeconds ?? 60}
          onResend={async () => {
            if (!emailVerification)
              throw new Error(
                "이메일 정보를 찾을 수 없어요. 처음부터 다시 시도해주세요.",
              );
            const result = await sendEmailVerificationApi(
              emailVerification.email,
            );
            setEmailVerification({
              email: emailVerification.email,
              verificationId: result.verification_id,
              expiresInSeconds: result.expires_in_seconds,
              resendAfterSeconds: result.resend_after_seconds,
              token: null,
            });
          }}
          onVerify={async (code) => {
            if (!emailVerification)
              throw new Error(
                "이메일 정보를 찾을 수 없어요. 처음부터 다시 시도해주세요.",
              );
            const result = await verifyEmailVerificationApi(
              emailVerification.verificationId,
              code,
            );
            setEmailVerification({
              ...emailVerification,
              token: result.verification_token,
            });
            pushScreen("signup-3");
          }}
          onContinue={() => pushScreen("signup-3")}
          onBack={() => goBackOrTo("signup-1")}
          userName={userName}
          onNavigate={navigate}
        />
      )}
      {screen === "signup-3" && (
        <SignupStep3
          // 가입 API 성공 후 JWT 로그인까지 완료하고 투자자 정보 확인으로 이동한다.
          onComplete={async (userId, password, phone) => {
            if (!emailVerification?.token) {
              throw new Error(
                "이메일 인증이 필요해요. 이메일 인증을 다시 진행해주세요.",
              );
            }
            const termCodeByAgreement = {
              b: "B_PRIVACY",
              c: "C_ASSOCIATE_TERMS",
              // AI_PERSONALIZATION은 투자성향 분석/챗봇 개인화 응답 제공 여부를 가르는 실제 권한
              // 경계로 쓰이고 있어(백엔드 recommendation.py의 has_ai_personalization_consent)
              // 자동으로 true를 채워보내지 않고, 사용자가 실제로 체크한 값을 그대로 전송한다.
              ai: "AI_PERSONALIZATION",
            } as const;
            const agreementByTermCode: Record<string, boolean> =
              Object.fromEntries(
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
              phone_number: phone,
              email: personal.email,
              email_verification_token: emailVerification.token,
              agreements: terms.map((term) => ({
                term_code: term.term_code,
                version: term.version,
                agreed: agreementByTermCode[term.term_code] ?? false,
              })),
            });
            setEmailVerification(null);
            // Strategy recommendation model 연결 전까지 onboarding flow에서 RiskResult를
            // 일시적으로 skip. 향후 추천 모델 연결 시 재활성화 예정.
            startInvestorProfile("strategy-list", undefined, "replace");
          }}
          onBack={() => goBackOrTo("signup-2")}
          userName={userName}
          onNavigate={navigate}
        />
      )}

      {screen === "risk" && (
        <RiskProfile
          notice={riskNotice}
          isSubmitting={isDiagnosisSubmitting}
          // postDiagnosisTarget이 'start'면 Strategy Detail "이 전략으로 시작하기"에서 온 것 —
          // 새 진입 state를 따로 만들지 않고 이미 있는 이 값을 그대로 재사용해 context를 판단한다.
          context={postDiagnosisTarget === "start" ? "strategy" : "general"}
          allowNonAiFallback={
            riskErrorCode === "AI_PERSONALIZATION_CONSENT_REQUIRED"
          }
          onContinueWithoutAi={() => {
            setRiskNotice(undefined);
            setRiskErrorCode(null);
            setPostDiagnosisTarget("risk-result");
            replaceScreen("strategy-list");
          }}
          onComplete={async (answers) => {
            setIsDiagnosisSubmitting(true);
            setRiskErrorCode(null);
            if (!accessToken) {
              setRiskNotice(
                "로그인 상태를 확인할 수 없어요. 다시 로그인한 뒤 시도해주세요.",
              );
              setIsDiagnosisSubmitting(false);
              return;
            }
            try {
              const response = await analyzeInvestorProfileApi(
                {
                  questionnaire_version: "v1",
                  answers: buildInvestorAnswerPayload(answers),
                },
                accessToken,
              );
              completeInvestorProfile(
                mapInvestorProfileResponse(response),
                answers,
                response.created_at,
                response.assessment_id,
              );
              setRiskNotice(undefined);
              setRiskErrorCode(null);
              // Strategy recommendation model 연결 전까지 onboarding flow에서 RiskResult를
              // 일시적으로 skip. 향후 추천 모델 연결 시 재활성화 예정.
              if (postDiagnosisTarget === "strategy-list") {
                setJustFinishedInvestorProfile(true);
              }
              replaceScreen(postDiagnosisTarget);
              setPostDiagnosisTarget("risk-result");
            } catch (error) {
              setRiskErrorCode(
                error instanceof ApiError ? error.code : "UNKNOWN_ERROR",
              );
              setRiskNotice(
                error instanceof Error
                  ? error.message
                  : "투자성향을 분석하지 못했어요. 잠시 후 다시 시도해주세요.",
              );
            } finally {
              setIsDiagnosisSubmitting(false);
            }
          }}
          onExit={() => goBackOrTo("home")}
        />
      )}
      {screen === "risk-result" && (
        <RiskResult userName={userName} onNavigate={navigate} />
      )}
      {screen === "investor-check" && (
        <InvestorProfileCheck
          userName={userName}
          onNavigate={navigate}
          onContinue={() => pushScreen("start")}
          onRediagnose={() => startInvestorProfile("start")}
        />
      )}

      {screen === "strategy-list" && (
        <StrategyList
          userName={userName}
          onNavigate={navigate}
          showOnboardingNotice={justFinishedInvestorProfile}
          onSelectLossAvoidance={() =>
            pushScreen("strategy-coming-soon-loss-avoidance")
          }
          onSelectF4={() => pushScreen("strategy-f4")}
          onSelectPersonalizedPreview={() => pushScreen("strategy-preview")}
        />
      )}
      {screen === "strategy-f4" && (
        <StrategyF4List
          userName={userName}
          onNavigate={navigate}
          onBack={() => goBackOrTo("strategy-list")}
          onSelectAvailableStrategy={() => {
            setStrategyRecommendation(null);
            pushScreen("strategy", {
              strategyId: "momentum",
              strategyDetailBackTarget: "strategy-f4",
            });
          }}
        />
      )}
      {screen === "strategy-coming-soon-loss-avoidance" && (
        <StrategyComingSoon
          strategyKey="loss-avoidance"
          userName={userName}
          onNavigate={navigate}
          onBack={() => goBackOrTo("strategy-list")}
        />
      )}
      {screen === "strategy-preview" && (
        <StrategyPersonalizedPreview
          userName={userName}
          onNavigate={navigate}
          onBack={() => goBackOrTo("strategy-list")}
        />
      )}
      {screen === "strategy" && strategy && (
        <StrategyDetail
          strategy={strategy}
          strategyCatalog={strategyCatalog}
          recommendation={
            strategyRecommendation?.strategy_id === strategy.id
              ? strategyRecommendation
              : null
          }
          userName={userName}
          onNavigate={navigate}
          onBack={() => goBackOrTo(strategyDetailBackTarget)}
          onStart={handleStartInvesting}
          onRequestLoginForBacktest={requestLoginForBacktest}
          onConfirmStrategyChange={confirmStrategyChange}
          pendingDeposit={
            pendingInvestment && pendingInvestment.strategyId === strategyId
              ? // InvestDeposit과 동일하게, 이미 보유한 잔액(대기 중인 투자와 같은 운용방식 계좌 기준)을 제외한 부족분만 안내한다
                {
                  amount: Math.max(
                    0,
                    pendingInvestment.amount -
                      (accountsByMode[pendingInvestment.mode]?.balance ?? 0),
                  ),
                }
              : null
          }
          onResumeDeposit={() => {
            if (!pendingInvestment) return;
            enterInvestmentStep(
              "invest-deposit",
              pendingInvestment.strategyId,
              pendingInvestment.amount,
              pendingInvestment.mode,
            );
          }}
        />
      )}
      {STRATEGY_DATA_SCREENS.includes(screen) && !screenStrategy && (
        <main
          className="flex min-h-screen flex-col items-center justify-center gap-5 bg-canvas px-8 text-center"
          role="alert"
        >
          <h1 className="text-[28px] font-bold">
            {isStrategyCatalogLoading
              ? "전략 정보를 불러오고 있어요"
              : "전략 정보를 불러오지 못했어요"}
          </h1>
          <p className="text-base text-muted">
            {isStrategyCatalogLoading
              ? "현재 전략 목록을 확인하고 있어요."
              : (strategyCatalogError ??
                "선택한 전략을 현재 목록에서 찾을 수 없어요.")}
          </p>
          {!isStrategyCatalogLoading && (
            <button
              onClick={() => setStrategyCatalogRetry((value) => value + 1)}
              className="rounded-field bg-lime px-8 py-4 text-base font-bold text-navy"
            >
              다시 시도하기
            </button>
          )}
        </main>
      )}
      {screen === "start" && strategy && (
        <StartInvesting
          userName={userName}
          strategyName={strategy.name}
          onNavigate={navigate}
          onStart={enterInvestmentFlow}
          onSelectStock={(code) => {
            pushScreen("stock", {
              stockCode: code,
              stockBackTarget: "start",
            });
          }}
        />
      )}
      {screen === "invest-terms" && strategy && (
        <InvestTerms
          userName={userName}
          strategy={strategy}
          amount={investmentAmount}
          mode={investmentMode}
          token={accessToken ?? ""}
          onNavigate={navigate}
          onBack={() => goBackInInvestmentFlow("invest-terms")}
          onComplete={(agreements: SignupPayload["agreements"]) => {
            setInvestmentAgreements(agreements);
            acceptStrategyTerms(strategyId);
            const step = resolveInvestmentEntryStep({
              strategyId,
              amount: investmentAmount,
              termsAcceptedStrategyIds: [
                ...termsAcceptedStrategyIds,
                strategyId,
              ],
              sesacAccount,
            });
            enterInvestmentStep(
              step,
              strategyId,
              investmentAmount,
              investmentMode,
              agreements,
            );
          }}
        />
      )}
      {screen === "invest-account" && strategy && (
        <InvestAccount
          userName={userName}
          strategyName={strategy.name}
          mode={investmentMode}
          otherModeAccount={(() => {
            const otherMode: OperationMode =
              investmentMode === "auto" ? "manual" : "auto";
            const otherAccount = accountsByMode[otherMode];
            return otherAccount
              ? { mode: otherMode, accountNumber: otherAccount.accountNumber }
              : null;
          })()}
          onNavigate={navigate}
          onBack={() => goBackInInvestmentFlow("invest-account")}
          onComplete={(account) => {
            connectSesacAccount(investmentMode, account);
            const step = resolveInvestmentEntryStep({
              strategyId,
              amount: investmentAmount,
              termsAcceptedStrategyIds,
              sesacAccount: account,
            });
            enterInvestmentStep(
              step,
              strategyId,
              investmentAmount,
              investmentMode,
            );
          }}
        />
      )}
      {screen === "invest-deposit" && sesacAccount && strategy && (
        <InvestDeposit
          userName={userName}
          strategyName={strategy.name}
          amount={investmentAmount}
          mode={investmentMode}
          account={sesacAccount}
          onNavigate={navigate}
          onBack={() => goBackInInvestmentFlow("invest-deposit")}
          onDeposit={(shortfall) => {
            deposit(investmentMode, shortfall);
            const step = resolveInvestmentEntryStep({
              strategyId,
              amount: investmentAmount,
              termsAcceptedStrategyIds,
              sesacAccount: {
                ...sesacAccount,
                balance: sesacAccount.balance + shortfall,
              },
            });
            enterInvestmentStep(
              step,
              strategyId,
              investmentAmount,
              investmentMode,
            );
          }}
          onDeferDeposit={() => {
            // Home 은 비로그인 전용 랜딩이라 로그인 상태가 반영되지 않는다 — 전략 상세로 돌려보낸다
            // (Header에 로그인 상태가 정상 표시되고, 필요하면 "이 전략으로 시작하기"로 바로 이 화면에 재진입할 수 있다)
            deferDeposit({
              strategyId,
              strategyName: strategy.name,
              amount: investmentAmount,
              mode: investmentMode,
            });
            clearInFlight();
            replaceScreen("strategy");
          }}
        />
      )}
      {screen === "invest-confirm" && sesacAccount && strategy && (
        <InvestConfirm
          userName={userName}
          strategyName={strategy.name}
          amount={investmentAmount}
          mode={investmentMode}
          account={sesacAccount}
          onNavigate={navigate}
          onBack={() => goBackInInvestmentFlow("invest-confirm")}
          onConfirm={async () => {
            if (!accessToken) {
              replaceScreen("login");
              throw new Error("로그인이 필요합니다.");
            }
            const operationMode = toAccountOperationMode(investmentMode);
            await startInvestmentApi(
              strategyId,
              investmentAmount,
              operationMode,
              investmentAgreements,
              accessToken,
            );
                        const account = await ensureAccount(
              accessToken,
              strategyId,
              operationMode,
            );
            if (strategyId === "momentum") {
              // 온보딩 완료 응답과 계좌 재조회가 서로 다른 시점에 도착할 수 있으므로,
              // 모델 추천 적용 직전에 현재 계좌의 전략을 서버에 명시적으로 확정한다.
              await selectStrategyApi(account.id, strategyId, accessToken);
              await applyLatestModelRecommendationsApi(account.id, accessToken);
              await ensureAccount(accessToken, strategyId, operationMode);
            }
            setActiveMode(investmentMode);
            // "계좌 1개 = 활성 전략 1개" — 실제 투자가 시작된 이 시점에만 계좌의 활성 전략을 기록한다
            setAccountActiveStrategy(investmentMode, strategyId);
            // 실제 투자가 시작된 시점 — 여기서만 DEPOSIT_PENDING을 해소한다
            clearPendingInvestment();
            clearInFlight();
            replaceScreen("portfolio");
          }}
        />
      )}

      {screen === "account-setup" && (
        <AccountSetup
          userName={userName}
          initialMode={activeMode ?? accountSetupMode}
          onNavigate={navigate}
          onBack={() => goBackOrTo("portfolio")}
          onComplete={prepareStandaloneAccount}
        />
      )}

      {screen === "account-deposit" && (
        <AccountDeposit
          userName={userName}
          mode={
            tradingAccount
              ? toOperationMode(tradingAccount.operation_mode)
              : accountSetupMode
          }
          account={tradingAccount}
          onNavigate={navigate}
          onBack={() => goBackOrTo("account-setup")}
          onDeposit={depositStandaloneCash}
          onDefer={() => replaceScreen("portfolio")}
        />
      )}

      {screen === "information" && (
        <InformationExam userName={userName} onNavigate={navigate} />
      )}

      {screen === "dashboard" && portfolioStrategy && (
        <Dashboard
          userName={userName}
          strategy={portfolioStrategy}
          mode={activeMode}
          onNavigate={navigate}
          onOpenHoldings={() => navigate("portfolio-detail")}
          onChangeStrategy={() => navigate("portfolio-detail")}
        />
      )}

      {/* 운용방식(activeMode)에 따라 요약 화면을 다르게 보여준다 — 반자동은 AI 제안을 사용자가 승인해야 하는
          Portfolio.tsx, 자동매매는 AI가 이미 실행을 마친 PortfolioAuto.tsx. 계좌를 아직 안 만든 경우(null)는
          기존 기본값인 반자동으로 보여준다. */}
      {screen === "portfolio" &&
        (activeMode === "auto" && tradingAccount?.selected_strategy_id ? (
                    <PortfolioAuto
            userName={userName}
            onNavigate={navigate}
            onAccountMissingAction={() => pushScreen("account-setup", { accountSetupMode: activeMode ?? "manual" })}
            onOpenDetail={() => pushScreen("portfolio-detail")}
            onOpenRebalanceAlerts={() => {
              pushScreen("rebalance-alerts", {
                rebalanceBackTarget: "portfolio",
              });
            }}
            onOpenFundManagement={(kind) => {
              // STEP1↔STEP2 사이에서만 쓰는 일회성 draft 금액 — 이전에 종료한 Flow에서 남은 값이
              // 새 Flow 진입 시 그대로 미리 채워져 보이지 않도록 매번 새로 시작할 때 0으로 되돌린다.
              if (kind === "deposit") {
                setFundAddAmount(0);
                pushScreen("fund-add");
              } else {
                setFundWithdrawAmount(0);
                pushScreen("fund-withdraw");
              }
            }}
          />
        ) : (
          <Portfolio
            userName={userName}
            onNavigate={navigate}
            onOpenDetail={() => pushScreen("portfolio-detail")}
            onOpenRebalanceAlerts={() => {
              pushScreen("rebalance-alerts", {
                rebalanceBackTarget: "portfolio",
              });
            }}
            onStartRiskProfile={() => startInvestorProfile("risk-result")}
            onSetupAccount={() => {
              pushScreen("account-setup", {
                accountSetupMode: activeMode ?? "manual",
              });
            }}
            onOpenFundManagement={(kind) => {
              // STEP1↔STEP2 사이에서만 쓰는 일회성 draft 금액 — 이전에 종료한 Flow에서 남은 값이
              // 새 Flow 진입 시 그대로 미리 채워져 보이지 않도록 매번 새로 시작할 때 0으로 되돌린다.
              if (kind === "deposit") {
                if (!tradingAccount?.selected_strategy_id) {
                  pushScreen("account-deposit", {
                    accountSetupMode: activeMode ?? "manual",
                  });
                } else {
                  setFundAddAmount(0);
                  pushScreen("fund-add");
                }
              } else {
                setFundWithdrawAmount(0);
                pushScreen("fund-withdraw");
              }
            }}
          />
        ))}

      {/* 추가 투자 STEP 1(금액) — portfolioStrategy가 없으면 아래 STRATEGY_DATA_SCREENS 가드가 대신 렌더링한다 */}
      {screen === "fund-add" && portfolioStrategy && (
        <FundAddAmount
          strategy={portfolioStrategy}
          initialAmount={fundAddAmount}
          userName={userName}
          onNavigate={navigate}
          onBack={() => goBackOrTo("portfolio")}
          onContinue={(amount) => {
            setFundAddAmount(amount);
            setFundOperationIdempotencyKey(`additional-${crypto.randomUUID()}`);
            pushScreen("fund-add-confirm");
          }}
        />
      )}

      {/* STEP 2(확인) — onConfirm은 실제 매수를 실행하지 않는다. Backend 추가투자 API contract가
         나오기 전까지는 STEP 3(fund-add-pending, FundManagementComingSoon 재사용)으로만 보낸다. */}
      {screen === "fund-add-confirm" && portfolioStrategy && (
        <FundAddConfirm
          strategy={portfolioStrategy}
          amount={fundAddAmount}
          userName={userName}
          onNavigate={navigate}
          onBack={() => goBackOrTo("fund-add")}
          isSubmitting={isFundOperationSubmitting}
          onConfirm={async () => {
            if (
              !accessToken ||
              !tradingAccount ||
              !fundOperationIdempotencyKey ||
              isFundOperationSubmitting
            )
              return;
            setFundOperationError(null);
            setIsFundOperationSubmitting(true);
            try {
              const operation = await createAdditionalInvestmentApi(
                tradingAccount.id,
                {
                  amount: fundAddAmount,
                  idempotency_key: fundOperationIdempotencyKey,
                },
                accessToken,
              );
              setFundOperation(operation);
              replaceScreen("fund-add-pending");
              void useTradingStore
                .getState()
                .refresh(accessToken, tradingAccount.operation_mode)
                .catch((error) => {
                  console.error(
                    "Fund operation succeeded, but portfolio refresh failed",
                    error,
                  );
                });
            } catch (error) {
              setFundOperationError(
                error instanceof ApiError
                  ? error.message
                  : "추가 투자에 실패했어요. 다시 시도해주세요.",
              );
            } finally {
              setIsFundOperationSubmitting(false);
            }
          }}
        />
      )}

      {/* 투자금 출금 STEP 1(금액) */}
      {screen === "fund-withdraw" && portfolioStrategy && (
        <FundWithdrawAmount
          strategy={portfolioStrategy}
          initialAmount={fundWithdrawAmount}
          userName={userName}
          onNavigate={navigate}
          onBack={() => goBackOrTo("portfolio")}
          onContinue={(amount) => {
            setFundWithdrawAmount(amount);
            setFundOperationIdempotencyKey(`withdrawal-${crypto.randomUUID()}`);
            pushScreen("fund-withdraw-confirm");
          }}
        />
      )}

      {/* STEP 2(확인) — onConfirm은 실제 매도/출금을 실행하지 않는다. Backend 출금 API contract가
         나오기 전까지는 STEP 3(fund-withdraw-pending, FundManagementComingSoon 재사용)으로만 보낸다. */}
      {screen === "fund-withdraw-confirm" && portfolioStrategy && (
        <FundWithdrawConfirm
          strategy={portfolioStrategy}
          amount={fundWithdrawAmount}
          userName={userName}
          onNavigate={navigate}
          onBack={() => goBackOrTo("fund-withdraw")}
          isSubmitting={isFundOperationSubmitting}
          onConfirm={async () => {
            if (
              !accessToken ||
              !tradingAccount ||
              !fundOperationIdempotencyKey ||
              isFundOperationSubmitting
            )
              return;
            setFundOperationError(null);
            setIsFundOperationSubmitting(true);
            try {
              const operation = await createWithdrawalApi(
                tradingAccount.id,
                {
                  amount: fundWithdrawAmount,
                  idempotency_key: fundOperationIdempotencyKey,
                },
                accessToken,
              );
              setFundOperation(operation);
              replaceScreen("fund-withdraw-pending");
              void useTradingStore
                .getState()
                .refresh(accessToken, tradingAccount.operation_mode)
                .catch((error) => {
                  console.error(
                    "Fund operation succeeded, but portfolio refresh failed",
                    error,
                  );
                });
            } catch (error) {
              setFundOperationError(
                error instanceof ApiError
                  ? error.message
                  : "출금에 실패했어요. 다시 시도해주세요.",
              );
            } finally {
              setIsFundOperationSubmitting(false);
            }
          }}
        />
      )}

      {(screen === "fund-add-pending" || screen === "fund-withdraw-pending") &&
        fundOperation && (
          <FundOperationResult
            kind={screen === "fund-add-pending" ? "deposit" : "withdraw"}
            operation={fundOperation}
            userName={userName}
            onNavigate={navigate}
            onDone={() => {
              setFundOperation(null);
              setFundAddAmount(0);
              setFundWithdrawAmount(0);
              setFundOperationIdempotencyKey(null);
              replaceScreen("portfolio");
            }}
          />
        )}
      {fundOperationError &&
        (screen === "fund-add-confirm" ||
          screen === "fund-withdraw-confirm") && (
          <div className="fixed bottom-6 left-1/2 z-[800] -translate-x-1/2 rounded-field bg-[#FBEAEA] px-6 py-4 text-sm font-semibold text-down shadow-lg">
            {fundOperationError}
          </div>
        )}

      {screen === "portfolio-detail" && portfolioStrategy && (
        <PortfolioDetail
          userName={userName}
          onAccountMissingAction={() => pushScreen("account-setup", { accountSetupMode: activeMode ?? "manual" })}
          strategy={portfolioStrategy}
          strategies={strategyCatalog}
          onStrategyChange={setStrategyId}
          onNavigate={navigate}
          onSelectStock={(code) => {
            pushScreen("stock", {
              stockCode: code,
              stockBackTarget: "portfolio-detail",
            });
          }}
          onSelectTransaction={(id) => {
            pushScreen("transaction-detail", {
              selectedTransactionId: id,
              transactionBackTarget: "portfolio-detail",
            });
          }}
          onOpenRebalanceAlerts={() => {
            pushScreen("rebalance-alerts", {
              rebalanceBackTarget: "portfolio-detail",
            });
          }}
          onRediagnose={() => startInvestorProfile("risk-result")}
          onBack={() => goBackOrTo("portfolio")}
        />
      )}

      {screen === "rebalance-alerts" && portfolioStrategy && (
                <RebalanceAlerts
          userName={userName}
          strategy={portfolioStrategy}
          onNavigate={navigate}
          onAccountMissingAction={() => pushScreen("account-setup", { accountSetupMode: activeMode ?? "manual" })}
          onBack={() => goBackOrTo(rebalanceBackTarget)}
          isAutoMode={activeMode === "auto"}
        />
      )}

      {screen === "all-holdings" && (
                <AllHoldings
          userName={userName}
          onNavigate={navigate}
          onAccountMissingAction={() => pushScreen("account-setup", { accountSetupMode: activeMode ?? "manual" })}
          onSelectStock={(code) => {
            pushScreen("stock", {
              stockCode: code,
              stockBackTarget: "all-holdings",
            });
          }}
          onBack={() => goBackOrTo("portfolio-detail")}
        />
      )}

      {screen === "transactions" && (
        <TransactionHistory
          userName={userName}
          onNavigate={navigate}
          onSelectTransaction={(id) => {
            pushScreen("transaction-detail", {
              selectedTransactionId: id,
              transactionBackTarget: "transactions",
            });
          }}
          onBack={() => goBackOrTo("portfolio-detail")}
        />
      )}

      {screen === "transaction-detail" && (
        <TransactionDetail
          transactionId={selectedTransactionId}
          backTarget={transactionBackTarget}
          userName={userName}
          onNavigate={navigate}
          onBack={() => goBackOrTo(transactionBackTarget)}
        />
      )}

      {screen === "stock" && (
        <StockDetail
          stockCode={stockCode}
          userName={userName}
          onNavigate={navigate}
          onBack={() => goBackOrTo(stockBackTarget)}
        />
      )}

      {/* 공개 금융 설명은 비로그인 사용자도 이용할 수 있고, 개인 계좌 조회만 Backend가 인증·동의를 검증한다. */}
      <Chatbot
        screen={screen}
        stockCode={stockCode}
        strategyId={strategyId}
        accountId={accessToken ? tradingAccount?.id : undefined}
      />
    </div>
  );
}
