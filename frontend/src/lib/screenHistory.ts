import type { OperationMode } from "../data/fees";
import type { Screen } from "../types";

export interface ScreenRoutePolicy {
  fallback: Screen;
}

/**
 * 앱의 모든 화면을 등록하는 라우팅 계약이다. 새 Screen을 추가하면서 이 표를 갱신하지 않으면
 * TypeScript가 빌드를 실패시켜 브라우저 뒤로가기 적용 누락을 막는다.
 */
export const SCREEN_ROUTE_POLICIES = {
  home: { fallback: "home" },
  login: { fallback: "home" },
  "start-signup": { fallback: "home" },
  "signup-1": { fallback: "start-signup" },
  "signup-2": { fallback: "signup-1" },
  "signup-3": { fallback: "signup-2" },
  risk: { fallback: "home" },
  "risk-result": { fallback: "risk" },
  "investor-check": { fallback: "strategy" },
  "strategy-list": { fallback: "home" },
  strategy: { fallback: "strategy-list" },
  start: { fallback: "strategy" },
  "strategy-f4": { fallback: "strategy-list" },
  "strategy-coming-soon-loss-avoidance": { fallback: "strategy-list" },
  "strategy-preview": { fallback: "strategy-list" },
  "invest-terms": { fallback: "start" },
  "invest-account": { fallback: "invest-terms" },
  "invest-deposit": { fallback: "invest-account" },
  "invest-confirm": { fallback: "invest-deposit" },
  "account-setup": { fallback: "portfolio" },
  "account-deposit": { fallback: "account-setup" },
  information: { fallback: "home" },
  dashboard: { fallback: "portfolio" },
  portfolio: { fallback: "home" },
  "portfolio-detail": { fallback: "portfolio" },
  stock: { fallback: "portfolio-detail" },
  transactions: { fallback: "portfolio-detail" },
  "transaction-detail": { fallback: "transactions" },
  "rebalance-alerts": { fallback: "portfolio-detail" },
  "all-holdings": { fallback: "portfolio-detail" },
  "fund-add": { fallback: "portfolio" },
  "fund-add-confirm": { fallback: "fund-add" },
  "fund-add-pending": { fallback: "portfolio" },
  "fund-withdraw": { fallback: "portfolio" },
  "fund-withdraw-confirm": { fallback: "fund-withdraw" },
  "fund-withdraw-pending": { fallback: "portfolio" },
} satisfies Record<Screen, ScreenRoutePolicy>;

export const ALL_SCREENS = Object.keys(SCREEN_ROUTE_POLICIES) as Screen[];

export interface ScreenHistoryContext {
  strategyId?: string;
  strategyDetailBackTarget?: Screen;
  stockCode?: string;
  stockBackTarget?: Screen;
  selectedTransactionId?: string;
  transactionBackTarget?: Screen;
  rebalanceBackTarget?: Screen;
  investmentMode?: OperationMode;
  accountSetupMode?: OperationMode;
  loginContext?: "header" | "strategy";
  postDiagnosisTarget?: Screen;
  pendingStartAfterLogin?: boolean;
  pendingReturnToStrategy?: boolean;
}

export interface FeinHistoryState {
  fein: true;
  version: 2;
  screen: Screen;
  depth: number;
  context: ScreenHistoryContext;
}

export interface HistoryPort {
  readonly state: unknown;
  pushState(data: unknown, unused: string): void;
  replaceState(data: unknown, unused: string): void;
  back(): void;
}

export function isScreen(value: unknown): value is Screen {
  return (
    typeof value === "string" &&
    Object.prototype.hasOwnProperty.call(SCREEN_ROUTE_POLICIES, value)
  );
}

export function fallbackScreen(screen: Screen): Screen {
  return SCREEN_ROUTE_POLICIES[screen].fallback;
}

export function createFeinHistoryState(
  screen: Screen,
  depth: number,
  context: ScreenHistoryContext,
): FeinHistoryState {
  return {
    fein: true,
    version: 2,
    screen,
    depth: Math.max(0, Math.trunc(depth)),
    context: { ...context },
  };
}

export function pushScreenHistory(
  history: HistoryPort,
  currentScreen: Screen,
  currentContext: ScreenHistoryContext,
  targetScreen: Screen,
  targetContext: ScreenHistoryContext,
): FeinHistoryState {
  const depth = parseFeinHistoryState(history.state)?.depth ?? 0;
  history.replaceState(
    createFeinHistoryState(currentScreen, depth, currentContext),
    "",
  );
  const next = createFeinHistoryState(
    targetScreen,
    depth + 1,
    targetContext,
  );
  history.pushState(next, "");
  return next;
}

export function replaceScreenHistory(
  history: HistoryPort,
  targetScreen: Screen,
  targetContext: ScreenHistoryContext,
): FeinHistoryState {
  const depth = parseFeinHistoryState(history.state)?.depth ?? 0;
  const next = createFeinHistoryState(targetScreen, depth, targetContext);
  history.replaceState(next, "");
  return next;
}

export function hasFeinBackEntry(history: HistoryPort): boolean {
  return (parseFeinHistoryState(history.state)?.depth ?? 0) > 0;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function optionalScreen(value: unknown): Screen | undefined {
  return isScreen(value) ? value : undefined;
}

/** 현재 버전과 기존 Phase 1 history.state를 모두 안전하게 읽는다. */
export function parseFeinHistoryState(value: unknown): FeinHistoryState | null {
  if (!value || typeof value !== "object") return null;
  const state = value as Record<string, unknown>;
  if (state.fein !== true || !isScreen(state.screen)) return null;

  const rawContext =
    state.context && typeof state.context === "object"
      ? (state.context as Record<string, unknown>)
      : {};
  const optionalOperationMode = (mode: unknown): OperationMode | undefined =>
    mode === "auto" || mode === "manual" ? mode : undefined;

  return createFeinHistoryState(
    state.screen,
    typeof state.depth === "number" && Number.isFinite(state.depth)
      ? state.depth
      : 0,
    {
      strategyId: optionalString(rawContext.strategyId),
      strategyDetailBackTarget: optionalScreen(
        rawContext.strategyDetailBackTarget,
      ),
      stockCode: optionalString(rawContext.stockCode),
      stockBackTarget: optionalScreen(rawContext.stockBackTarget),
      selectedTransactionId: optionalString(rawContext.selectedTransactionId),
      transactionBackTarget: optionalScreen(rawContext.transactionBackTarget),
      rebalanceBackTarget: optionalScreen(rawContext.rebalanceBackTarget),
      investmentMode: optionalOperationMode(rawContext.investmentMode),
      accountSetupMode: optionalOperationMode(rawContext.accountSetupMode),
      loginContext:
        rawContext.loginContext === "header" ||
        rawContext.loginContext === "strategy"
          ? rawContext.loginContext
          : undefined,
      postDiagnosisTarget: optionalScreen(rawContext.postDiagnosisTarget),
      pendingStartAfterLogin:
        typeof rawContext.pendingStartAfterLogin === "boolean"
          ? rawContext.pendingStartAfterLogin
          : undefined,
      pendingReturnToStrategy:
        typeof rawContext.pendingReturnToStrategy === "boolean"
          ? rawContext.pendingReturnToStrategy
          : undefined,
    },
  );
}
