import { useEffect, useState } from 'react';
import Chatbot from './components/Chatbot';
import Dashboard from './pages/Dashboard';
import Home from './pages/Home';
import InformationExam from './pages/InformationExam';
import InvestAccount from './pages/InvestAccount';
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
import { resolveInvestmentEntryStep } from './lib/investmentFlow';
import { useAuthStore } from './store/authStore';
import { useInvestmentStore } from './store/investmentStore';
import type { Screen, SignupPersonal } from './types';

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
  const termsAcceptedStrategyIds = useInvestmentStore((s) => s.termsAcceptedStrategyIds);
  const sesacAccount = useInvestmentStore((s) => s.sesacAccount);
  const pendingInvestment = useInvestmentStore((s) => s.pendingInvestment);
  const acceptStrategyTerms = useInvestmentStore((s) => s.acceptStrategyTerms);
  const connectSesacAccount = useInvestmentStore((s) => s.connectSesacAccount);
  const deposit = useInvestmentStore((s) => s.deposit);
  const deferDeposit = useInvestmentStore((s) => s.deferDeposit);

  /** StartInvesting "이대로 시작하기" — 이미 완료한 단계는 건너뛰고 다음 필요한 단계로 이동한다 */
  const enterInvestmentFlow = (amount: number, mode: OperationMode) => {
    setInvestmentAmount(amount);
    setInvestmentMode(mode);
    setScreen(resolveInvestmentEntryStep({ strategyId, amount, termsAcceptedStrategyIds, sesacAccount }));
  };

  /**
   * Header "나의 포트폴리오"/로그인 성공 등 Portfolio로 향하는 모든 경로가 거치는 관문.
   * DEPOSIT_PENDING(계좌는 연결됐지만 입금이 남은) 상태라면 Portfolio 대신 입금 요청 화면으로 보낸다.
   */
  const navigate = (target: Screen) => {
    if (target === 'portfolio' && pendingInvestment) {
      setStrategyId(pendingInvestment.strategyId);
      setInvestmentAmount(pendingInvestment.amount);
      setInvestmentMode(pendingInvestment.mode);
      setScreen('invest-deposit');
      return;
    }
    setScreen(target);
  };

  const userName = authenticatedUser?.name ?? (personal.name.trim() || '서연');

  useEffect(() => { void initialize(); }, [initialize]);

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
          onBack={() => setScreen('start')}
          onComplete={() => {
            acceptStrategyTerms(strategyId);
            setScreen(resolveInvestmentEntryStep({
              strategyId,
              amount: investmentAmount,
              termsAcceptedStrategyIds: [...termsAcceptedStrategyIds, strategyId],
              sesacAccount,
            }));
          }}
        />
      )}
      {screen === 'invest-account' && (
        <InvestAccount
          userName={userName}
          strategyName={strategy.name}
          onNavigate={navigate}
          onBack={() => setScreen('invest-terms')}
          onComplete={(account) => {
            connectSesacAccount(account);
            setScreen(resolveInvestmentEntryStep({
              strategyId, amount: investmentAmount, termsAcceptedStrategyIds, sesacAccount: account,
            }));
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
          onBack={() => setScreen('invest-account')}
          onDeposit={() => {
            deposit(investmentAmount);
            setScreen(resolveInvestmentEntryStep({
              strategyId,
              amount: investmentAmount,
              termsAcceptedStrategyIds,
              sesacAccount: { ...sesacAccount, balance: sesacAccount.balance + investmentAmount },
            }));
          }}
          onDeferDeposit={() => {
            // Home 은 비로그인 전용 랜딩이라 로그인 상태가 반영되지 않는다 — 전략 상세로 돌려보낸다
            // (Header에 로그인 상태가 정상 표시되고, 필요하면 "이 전략으로 시작하기"로 바로 이 화면에 재진입할 수 있다)
            deferDeposit({ strategyId, strategyName: strategy.name, amount: investmentAmount, mode: investmentMode });
            setScreen('strategy');
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
