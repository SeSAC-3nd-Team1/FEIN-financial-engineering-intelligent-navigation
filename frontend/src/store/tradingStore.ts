import { create } from 'zustand';
import {
  ApiError,
  createAccountApi,
  createOrderApi,
  createRebalancingDecisionApi,
  getExecutionsApi,
  getMyAccountApi,
  getOrdersApi,
  getPortfolioApi,
  getRebalancingDecisionsApi,
  selectStrategyApi,
  type AccountOperationMode,
  type AccountResponse,
  type ExecutionResponse,
  type OrderCreateRequest,
  type OrderResponse,
  type PortfolioResponse,
  type RebalancingDecisionCreateRequest,
  type RebalancingDecisionHistoryResponse,
} from '../lib/backendApi';
import { mergeDecisionHistory } from '../lib/portfolioAnalyticsModel';

interface TradingState {
  account: AccountResponse | null;
  portfolio: PortfolioResponse | null;
  decisions: RebalancingDecisionHistoryResponse | null;
  orders: OrderResponse[];
  executions: ExecutionResponse[];
  accountMissing: boolean;
  isLoading: boolean;
  isRefreshing: boolean;
  isSubmitting: boolean;
  isDecisionSubmitting: boolean;
  lastUpdatedAt: string | null;
  error: ApiError | null;
  orderMessage: string | null;
  refresh: (token: string, mode: AccountOperationMode) => Promise<void>;
  ensureAccount: (
    token: string,
    strategyId: string,
    mode: AccountOperationMode,
    initialDeposit?: number,
  ) => Promise<AccountResponse>;
  placeOrder: (token: string, payload: OrderCreateRequest) => Promise<OrderResponse>;
  recordDecision: (token: string, payload: RebalancingDecisionCreateRequest) => Promise<void>;
  clearError: () => void;
  clear: () => void;
}

const EMPTY_STATE = {
  account: null,
  portfolio: null,
  decisions: null,
  orders: [],
  executions: [],
  accountMissing: false,
  isLoading: false,
  isRefreshing: false,
  isSubmitting: false,
  isDecisionSubmitting: false,
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
  const [portfolio, orders, executions, decisions] = await Promise.all([
    getPortfolioApi(account.id, token),
    getOrdersApi(account.id, token),
    getExecutionsApi(account.id, token),
    getRebalancingDecisionsApi(account.id, token),
  ]);
  return { portfolio, orders, executions, decisions };
}

let activeRefresh: { key: string; promise: Promise<void> } | null = null;
let refreshGeneration = 0;

export const useTradingStore = create<TradingState>((set, get) => ({
  ...EMPTY_STATE,

  refresh: async (token, mode) => {
    // 같은 (토큰, 운용방식) 조합으로 이미 진행 중인 refresh 가 있으면 그걸 그대로 기다린다.
    // 운용방식이 바뀌면(반자동<->자동) 다른 계좌를 조회해야 하므로 새 refresh 를 시작해야 한다.
    const key = `${token}:${mode}`;
    if (activeRefresh?.key === key) return activeRefresh.promise;
    const generation = ++refreshGeneration;
    const promise = (async () => {
      set((state) => ({
        isLoading: !state.account,
        isRefreshing: Boolean(state.account),
        error: null,
      }));
      try {
        const account = await getMyAccountApi(token, mode);
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
            account: null, portfolio: null, decisions: null, orders: [], executions: [], accountMissing: true,
            isLoading: false, isRefreshing: false, error: null,
          });
          return;
        }
        set({ error: apiError, isLoading: false, isRefreshing: false });
        throw apiError;
      }
    })();
    activeRefresh = { key, promise };
    try {
      await promise;
    } finally {
      if (activeRefresh?.promise === promise) activeRefresh = null;
    }
  },

  ensureAccount: async (token, strategyId, mode, initialDeposit) => {
    set({ isSubmitting: true, error: null, orderMessage: null });
    try {
      let account: AccountResponse;
      try {
        account = await getMyAccountApi(token, mode);
      } catch (error) {
        const apiError = asApiError(error);
        if (apiError.code !== 'ACCOUNT_NOT_FOUND') throw apiError;
        account = await createAccountApi('나의 가상 투자계좌', mode, token, initialDeposit);
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
      // placeOrder 는 항상 이미 로드된 계좌(get().account)가 있는 상태에서만 호출된다 — 계좌가 없다면
      // 애초에 주문 화면에 진입할 수 없다. 그래도 방어적으로 폴백할 때는 반자동(기본값)으로 조회한다.
      const account = get().account ?? await getMyAccountApi(token, 'SEMI_AUTO');
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

  recordDecision: async (token, payload) => {
    if (get().isDecisionSubmitting) {
      throw new ApiError('DECISION_IN_PROGRESS', '판단을 기록하고 있습니다.', 409);
    }
    set({ isDecisionSubmitting: true, error: null });
    try {
      const decision = await createRebalancingDecisionApi(payload, token);
      set((state) => ({
        decisions: mergeDecisionHistory(state.decisions, decision),
        isDecisionSubmitting: false,
      }));
    } catch (error) {
      const apiError = asApiError(error);
      set({ error: apiError, isDecisionSubmitting: false });
      throw apiError;
    }
  },

  clearError: () => set({ error: null, orderMessage: null }),
  clear: () => {
    refreshGeneration += 1;
    set(EMPTY_STATE);
  },
}));
