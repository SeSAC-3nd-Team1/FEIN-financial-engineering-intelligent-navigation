import { describe, expect, it } from "vitest";

import type { Screen } from "../types";
import {
  ALL_SCREENS,
  createFeinHistoryState,
  fallbackScreen,
  parseFeinHistoryState,
  SCREEN_ROUTE_POLICIES,
} from "./screenHistory";

const EXPECTED_SCREENS: Screen[] = [
  "home",
  "login",
  "start-signup",
  "signup-1",
  "signup-2",
  "signup-3",
  "risk",
  "risk-result",
  "investor-check",
  "strategy-list",
  "strategy",
  "start",
  "strategy-f4",
  "strategy-coming-soon-loss-avoidance",
  "strategy-preview",
  "invest-terms",
  "invest-account",
  "invest-deposit",
  "invest-confirm",
  "account-setup",
  "account-deposit",
  "information",
  "dashboard",
  "portfolio",
  "portfolio-detail",
  "stock",
  "transactions",
  "transaction-detail",
  "rebalance-alerts",
  "all-holdings",
  "fund-add",
  "fund-add-confirm",
  "fund-add-pending",
  "fund-withdraw",
  "fund-withdraw-confirm",
  "fund-withdraw-pending",
];

describe("screen history route contract", () => {
  it("registers every Screen exactly once", () => {
    expect(new Set(ALL_SCREENS)).toEqual(new Set(EXPECTED_SCREENS));
    expect(ALL_SCREENS).toHaveLength(EXPECTED_SCREENS.length);
    expect(Object.keys(SCREEN_ROUTE_POLICIES)).toHaveLength(36);
  });

  it("provides a valid fallback for every screen", () => {
    for (const screen of EXPECTED_SCREENS) {
      expect(EXPECTED_SCREENS).toContain(fallbackScreen(screen));
    }
  });
});

describe("screen history state", () => {
  it("round-trips route context needed by detail screens", () => {
    const state = createFeinHistoryState("stock", 3, {
      strategyId: "momentum",
      stockCode: "005930",
      stockBackTarget: "all-holdings",
      operationMode: "manual",
    });

    expect(parseFeinHistoryState(state)).toEqual(state);
  });

  it("accepts legacy Phase 1 state without context", () => {
    expect(
      parseFeinHistoryState({ fein: true, screen: "signup-2", depth: 2 }),
    ).toEqual(createFeinHistoryState("signup-2", 2, {}));
  });

  it("rejects unknown screens and sanitizes invalid context", () => {
    expect(parseFeinHistoryState({ fein: true, screen: "missing" })).toBeNull();
    expect(
      parseFeinHistoryState({
        fein: true,
        screen: "stock",
        depth: -4,
        context: {
          stockCode: 5930,
          stockBackTarget: "missing",
          operationMode: "AUTO",
        },
      }),
    ).toEqual(createFeinHistoryState("stock", 0, {}));
  });
});
