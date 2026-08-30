import { toAccountOperationMode } from '../data/fees';
import { useAuthStore } from '../store/authStore';
import { useInvestmentStore } from '../store/investmentStore';
import { useTradingStore } from '../store/tradingStore';

export function useTradingRetry() {
  const token = useAuthStore((state) => state.accessToken);
  const logout = useAuthStore((state) => state.logout);
  const mode = toAccountOperationMode(
    useInvestmentStore((state) => state.activeMode),
  );
  const refresh = useTradingStore((state) => state.refresh);
  return () => {
    if (token) {
      void refresh(token, mode).catch((error: { status?: number }) => {
        if (error.status === 401) void logout();
      });
    }
  };
}
