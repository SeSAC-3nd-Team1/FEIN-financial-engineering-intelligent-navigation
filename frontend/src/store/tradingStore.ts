import { create } from 'zustand';
import {
  ApiError,
  createAccountApi,
  createOrderApi,
  getExecutionsApi,
  getMyAccountApi,
  getOrdersApi,
  getPortfolioApi,
  selectStrategyApi,
  type AccountResponse,
  type ExecutionResponse,
  type OrderCreateRequest,
  type OrderResponse,
  type PortfolioResponse,
} from '../lib/backendApi';

interface TradingState {
  account: AccountResponse | null;
  portfolio: PortfolioResponse | null;
  orders: OrderResponse[];
  executions: ExecutionResponse[];
  accountMissing: boolean;
  isLoading: boolean;
  isRefreshing: boolean;
  isSubmitting: boolean;
  lastUpdatedAt: string | null;
  error: ApiError | null;
  orderMessage: string | null;
  refresh: (token: string) => Promise<void>;
  ensureAccount: (token: string, strategyId: string) => Promise<AccountResponse>;
  placeOrder: (token: string, payload: OrderCreateRequest) => Promise<OrderResponse>;
  clearError: () => void;
  clear: () => void;
}

const EMPTY_STATE = {
  account: null,
  portfolio: null,
  orders: [],
  executions: [],
  accountMissing: false,
  isLoading: false,
  isRefreshing: false,
  isSubmitting: false,
  lastUpdatedAt: null,
  error: null,
  orderMessage: null,
};

function asApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError('UNKNOWN_ERROR', '요청을 처리하지 못했습니다.', 0);
}

async function loadAccountData(account: AccountResponse, token: string) {
  const [portfolio, orders, executions] = await Promise.all([
    getPortfolioApi(account.id, token),
    getOrdersApi(account.id, token),
    getExecutionsApi(account.id, token),
  ]);
  return { portfolio, orders, executions };
}

let activeRefresh: { token: string; promise: Promise<void> } | null = null;
let refreshGeneration = 0;

export const useTradingStore = create<TradingState>((set, get) => ({
  ...EMPTY_STATE,

  refresh: async (token) => {
    if (activeRefresh?.token === token) return activeRefresh.promise;
    const generation = ++refreshGeneration;
    const promise = (async () => {
      set((state) => ({
        isLoading: !state.account,
        isRefreshing: Boolean(state.account),
        error: null,
      }));
      try {
        const account = await getMyAccountApi(token);
        if (generation !== refreshGeneration) return;
        set({ account, accountMissing: false });
        const data = await loadAccountData(account, token);
        if (generation !== refreshGeneration) return;
        set({ ...data, isLoading: false, isRefreshing: false, lastUpdatedAt: new Date().toISOString() });
      } catch (error) {
        if (generation !== refreshGeneration) return;
        const apiError = asApiError(error);
        if (apiError.code === 'ACCOUNT_NOT_FOUND') {
          set({
            account: null, portfolio: null, orders: [], executions: [], accountMissing: true,
            isLoading: false, isRefreshing: false, error: null,
          });
          return;
        }
        set({ error: apiError, isLoading: false, isRefreshing: false });
        throw apiError;
      }
    })();
    activeRefresh = { token, promise };
    try {
      await promise;
    } finally {
      if (activeRefresh?.promise === promise) activeRefresh = null;
    }
  },

  ensureAccount: async (token, strategyId) => {
    set({ isSubmitting: true, error: null, orderMessage: null });
    try {
      let account: AccountResponse;
      try {
        account = await getMyAccountApi(token);
      } catch (error) {
        const apiError = asApiError(error);
        if (apiError.code !== 'ACCOUNT_NOT_FOUND') throw apiError;
        account = await createAccountApi('나의 가상 투자계좌', token);
      }
      if (account.selected_strategy_id !== strategyId) {
        account = await selectStrategyApi(account.id, strategyId, token);
      }
      const data = await loadAccountData(account, token);
      set({ account, ...data, accountMissing: false, isSubmitting: false, lastUpdatedAt: new Date().toISOString() });
      return account;
    } catch (error) {
      const apiError = asApiError(error);
      set({ error: apiError, isSubmitting: false });
      throw apiError;
    }
  },

  placeOrder: async (token, payload) => {
    if (get().isSubmitting) {
      throw new ApiError('ORDER_IN_PROGRESS', '처리 중인 주문이 있습니다.', 409);
    }
    set({ isSubmitting: true, error: null, orderMessage: null });
    try {
      const order = await createOrderApi(payload, token);
      const account = get().account ?? await getMyAccountApi(token);
      const data = await loadAccountData(account, token);
      set({
        account, ...data, isSubmitting: false, lastUpdatedAt: new Date().toISOString(),
        orderMessage: `${order.stock_code} ${order.side === 'BUY' ? '매수' : '매도'} 주문이 체결됐습니다.`,
      });
      return order;
    } catch (error) {
      const apiError = asApiError(error);
      set({ error: apiError, isSubmitting: false });
      throw apiError;
    }
  },

  clearError: () => set({ error: null, orderMessage: null }),
  clear: () => {
    refreshGeneration += 1;
    set(EMPTY_STATE);
  },
}));
