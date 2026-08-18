import { useState } from 'react';
import Chatbot from './components/Chatbot';
import Dashboard from './pages/Dashboard';
import Home from './pages/Home';
import InformationExam from './pages/InformationExam';
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
 *        → risk(인트로·Q1~Q5·완료) → risk-result
 *        → strategy → start → portfolio(20종목) → stock(종목 상세)
 *   information 은 헤더 "정보"에서 언제든 진입
 *
 *   로그인 성공, 투자 시작 완료, 헤더 "나의 포트폴리오" 클릭은 모두 동일하게
 *   portfolio(Power BI 분석 대시보드)로 착지한다. dashboard 는 portfolio 상단의
 *   "← 대시보드로 돌아가기"로만 진입하는 보조 요약 화면이다.
 *
 * 챗봇 FAB 는 라우팅 밖에 있어 모든 화면에 상주한다.
 */
export default function App() {
  const [screen, setScreen] = useState<Screen>('home');
  const [personal, setPersonal] = useState<SignupPersonal>({ name: '', birthdate: '', phone: '' });
  const [strategyId, setStrategyId] = useState('low');
  const [strategy, setStrategy] = useState<Strategy>('저변동성');
  const [stockIndex, setStockIndex] = useState(0);
  const login = useAuthStore((s) => s.login);

  const userName = personal.name.trim() || '서연';

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
          // 가입 완료 → 인증 state를 켜고 투자성향 진단으로 이동
          onComplete={() => { login(); setScreen('risk'); }}
          onBack={() => setScreen('signup-2')}
          userName={userName}
          onNavigate={setScreen}
        />
      )}

      {screen === 'risk' && (
        <RiskProfile onComplete={() => setScreen('risk-result')} onExit={() => setScreen('home')} />
      )}
      {screen === 'risk-result' && (
        <RiskResult
          userName={userName}
          onNavigate={setScreen}
          onSelectStrategy={(id) => { setStrategyId(id); setScreen('strategy'); }}
        />
      )}

      {screen === 'strategy' && (
        <StrategyDetail
          strategyId={strategyId}
          userName={userName}
          onNavigate={setScreen}
          onStart={() => setScreen('start')}
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
          onRediagnose={() => setScreen('risk')}
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
