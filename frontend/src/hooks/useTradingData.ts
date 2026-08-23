import { useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useTradingStore } from '../store/tradingStore';

/** 현재 화면에서 필요한 계좌/포트폴리오 bundle을 한 번에 조회한다. */
export function useTradingData() {
  const token = useAuthStore((state) => state.accessToken);
  const logout = useAuthStore((state) => state.logout);
  const refresh = useTradingStore((state) => state.refresh);
  const clear = useTradingStore((state) => state.clear);

  useEffect(() => {
    if (!token) {
      clear();
      return;
    }
    void refresh(token).catch((error: { status?: number }) => {
      if (error.status === 401) void logout();
    });
  }, [clear, logout, refresh, token]);

  return token;
}
