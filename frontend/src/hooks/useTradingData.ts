import { useEffect } from 'react';
import { toAccountOperationMode } from '../data/fees';
import { useAuthStore } from '../store/authStore';
import { useInvestmentStore } from '../store/investmentStore';
import { useTradingStore } from '../store/tradingStore';

/** 현재 화면에서 필요한 계좌/포트폴리오 bundle을 한 번에 조회한다.
 *  운용방식(자동/반자동)마다 별도 계좌라, activeMode 에 맞는 계좌를 불러온다 —
 *  activeMode 가 아직 없으면(계좌를 만들기 전) 반자동 계좌 기준으로 조회한다. */
export function useTradingData() {
  const token = useAuthStore((state) => state.accessToken);
  const logout = useAuthStore((state) => state.logout);
  const activeMode = useInvestmentStore((state) => state.activeMode);
  const refresh = useTradingStore((state) => state.refresh);
  const clear = useTradingStore((state) => state.clear);
  const mode = toAccountOperationMode(activeMode);

  useEffect(() => {
    if (!token) {
      clear();
      return;
    }
    void refresh(token, mode).catch((error: { status?: number }) => {
      if (error.status === 401) void logout();
    });
  }, [clear, logout, refresh, token, mode]);

  return token;
}
