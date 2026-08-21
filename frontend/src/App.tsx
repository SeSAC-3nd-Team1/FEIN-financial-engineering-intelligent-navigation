import { useState } from 'react';
import Backtest from './pages/Backtest';
import Chatbot from './components/Chatbot';
import Dashboard from './pages/Dashboard';
import Home from './pages/Home';
import InformationExam from './pages/InformationExam';
import InvestorProfileCheck from './pages/InvestorProfileCheck';
import Login from './pages/Login';
import Portfolio, { type Strategy } from './pages/Portfolio';
import RiskProfile from './pages/RiskProfile';
import RiskResult from './pages/RiskResult';
import SignupStep1 from './pages/SignupStep1';
import SignupStep2 from './pages/SignupStep2';
import SignupStep3 from './pages/SignupStep3';
import StartInvesting from './pages/StartInvesting';
import StockDetail from './pages/StockDetail';
import StrategyDetail from './pages/StrategyDetail';
import { useAuthStore } from './store/authStore';
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
  });
  const [strategyId, setStrategyId] = useState('low');
  const [strategy, setStrategy] = useState<Strategy>('저변동성');
  const [stockIndex, setStockIndex] = useState(0);
  // 투자자 정보 확인(risk) 완료 후 어디로 이어갈지 + 진입 맥락(안내 문구)
  const [postDiagnosisTarget, setPostDiagnosisTarget] = useState<Screen>('risk-result');
  const [riskNotice, setRiskNotice] = useState<string | undefined>(undefined);
  const login = useAuthStore((s) => s.login);
  const register = useAuthStore((s) => s.register);
  const investorProfileCompleted = useAuthStore((s) => s.investorProfileCompleted);
  const completeInvestorProfile = useAuthStore((s) => s.completeInvestorProfile);

  const userName = personal.name.trim() || '서연';

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
      {screen === 'home' && <Home onNavigate={setScreen} />}

      {screen === 'login' && (
        <Login
          // 로그인 성공 → 인증 state를 켜고, 헤더 "나의 포트폴리오"와 동일한 목적지(Portfolio)로 이동
          onLogin={() => { login(); setScreen('portfolio'); }}
          onSignup={() => setScreen('signup-1')}
          onHome={() => setScreen('home')}
          onNavigate={setScreen}
        />
      )}

      {screen === 'signup-1' && (
        <SignupStep1
          value={personal}
          onChange={setPersonal}
          onNext={() => setScreen('signup-2')}
          userName={userName}
          onNavigate={setScreen}
        />
      )}
      {screen === 'signup-2' && (
        <SignupStep2
          phone={personal.phone}
          onNext={() => setScreen('signup-3')}
          onBack={() => setScreen('signup-1')}
          userName={userName}
          onNavigate={setScreen}
        />
      )}
      {screen === 'signup-3' && (
        <SignupStep3
          // 가입 완료 → 아이디/비밀번호를 저장해두고(로그인 시 대조용), 인증 state를 켜서
          // 회원가입과는 별도 단계인 투자자 정보 확인으로 이동
          onComplete={(userId, password) => {
            register(userId, password);
            login();
            startInvestorProfile('risk-result');
          }}
          onBack={() => setScreen('signup-2')}
          userName={userName}
          onNavigate={setScreen}
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
          onNavigate={setScreen}
          onSelectStrategy={(id) => { setStrategyId(id); setScreen('strategy'); }}
        />
      )}
      {screen === 'investor-check' && (
        <InvestorProfileCheck
          userName={userName}
          onNavigate={setScreen}
          onContinue={() => setScreen('start')}
          onRediagnose={() => startInvestorProfile('start')}
        />
      )}

      {screen === 'strategy' && (
        <StrategyDetail
          strategyId={strategyId}
          userName={userName}
          onNavigate={setScreen}
          onStart={handleStartInvesting}
          onOpenBacktest={() => setScreen('backtest')}
        />
      )}
      {screen === 'backtest' && (
        <Backtest
          strategyId={strategyId}
          userName={userName}
          onNavigate={setScreen}
          onBack={() => setScreen('strategy')}
        />
      )}
      {screen === 'start' && (
        // 투자 시작 완료 → 이제 막 포트폴리오가 생긴 상태이므로, 로그인 착지점과 동일하게 Portfolio로 이동
        <StartInvesting userName={userName} onNavigate={setScreen} onStart={() => setScreen('portfolio')} />
      )}

      {screen === 'information' && <InformationExam userName={userName} onNavigate={setScreen} />}

      {screen === 'dashboard' && (
        <Dashboard
          userName={userName}
          strategyName={`${strategy} 전략`}
          onNavigate={setScreen}
          onOpenHoldings={() => setScreen('portfolio')}
          onChangeStrategy={() => setScreen('portfolio')}
        />
      )}

      {screen === 'portfolio' && (
        <Portfolio
          userName={userName}
          strategy={strategy}
          onStrategyChange={setStrategy}
          onNavigate={setScreen}
          onSelectStock={(i) => { setStockIndex(i); setScreen('stock'); }}
          onRediagnose={() => startInvestorProfile('risk-result')}
          onBack={() => setScreen('dashboard')}
        />
      )}

      {screen === 'stock' && (
        <StockDetail
          index={stockIndex}
          userName={userName}
          onNavigate={setScreen}
          onBack={() => setScreen('portfolio')}
        />
      )}

      {/* 전 화면 상주 플로팅 챗봇 */}
      <Chatbot />
    </div>
  );
}
