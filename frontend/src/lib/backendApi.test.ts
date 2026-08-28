import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  applyLatestModelRecommendationsApi,
  createStrategyRecommendationApi,
  depositAccountCashApi,
  getLatestModelRecommendationsApi,
  startInvestmentApi,
  type ModelRecommendationSnapshotResponse,
  type StrategyRecommendationResponse,
} from "./backendApi";

const recommendation: StrategyRecommendationResponse = {
  recommendation_id: "recommendation-1",
  assessment_id: "assessment-1",
  primary: {
    strategy_id: "value",
    rank: 1,
    score: 0.84,
    match_level: "BEST",
    reason: "균형 성향과 잘 맞습니다.",
    caution: "회복까지 시간이 걸릴 수 있습니다.",
  },
  alternatives: [],
  model_version: "strategy-recommender-v1",
  dataset_version: "financial-8y-v1",
  recommendation_version: "v1",
  created_at: "2026-08-27T00:00:00Z",
};

const modelSnapshot: ModelRecommendationSnapshotResponse = {
  as_of: "2026-08-26",
  generated_at: "2026-08-26T09:00:00Z",
  model_version: "price-momentum-v1",
  data_version: "algorithm-ohlcv-v2",
  status: "ready",
  market_regime: "neutral",
  source: "generated",
  is_stale: false,
  recommendations: [
    {
      symbol: "005930",
      stock_name: "삼성전자",
      score: 0.82,
      rank: 1,
      target_weight: 0.2,
      reason: "120일 가격 모멘텀 상위 종목",
    },
  ],
};

describe("strategy recommendation API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("assessment id와 인증 토큰으로 실제 추천 생성 endpoint를 호출한다", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(recommendation), { status: 201 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      createStrategyRecommendationApi("assessment-1", "token-a"),
    ).resolves.toEqual(recommendation);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/strategy-recommendations",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ assessment_id: "assessment-1" }),
        headers: expect.any(Headers),
      }),
    );
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Headers).get("Authorization")).toBe(
      "Bearer token-a",
    );
  });

  it("인증 토큰으로 최신 가격 모델 추천을 조회한다", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(modelSnapshot)));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getLatestModelRecommendationsApi("token-a")).resolves.toEqual(
      modelSnapshot,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/model-recommendations/latest",
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    );
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Headers).get("Authorization")).toBe(
      "Bearer token-a",
    );
  });

  it("선택 계좌에 최신 모멘텀 추천 적용을 요청한다", async () => {
    const applied = {
      account_id: "account-1",
      strategy_id: "momentum",
      as_of: "2026-08-25",
      target_count: 5,
      orders_created: 5,
      status: "APPLIED",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(applied)));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      applyLatestModelRecommendationsApi("account-1", "token-a"),
    ).resolves.toEqual(applied);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/model-recommendations/latest/apply",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ account_id: "account-1" }),
      }),
    );
  });

  it("선택 동의 오류의 backend code를 ApiError에 보존한다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: "AI_PERSONALIZATION_CONSENT_REQUIRED",
            message: "AI 기반 맞춤형 서비스 이용 동의가 필요합니다.",
          }),
          { status: 403 },
        ),
      ),
    );

    const error = await createStrategyRecommendationApi(
      "assessment-1",
      "token-a",
    ).catch((reason) => reason);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      code: "AI_PERSONALIZATION_CONSENT_REQUIRED",
      status: 403,
    });
  });
});

describe("investment onboarding API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("실제 약관·계좌·입금·완료 API를 순서대로 호출한다", async () => {
    const baseOnboarding = {
      id: "onboarding-1",
      strategy_id: "momentum",
      investment_amount: "10000000",
      operation_mode: "AUTO" as const,
      status: "TERMS_PENDING" as const,
      account_id: null,
      terms_completed: false,
      account_exists: false,
      next_step: "TERMS" as const,
      completed_at: null,
      created_at: "2026-08-27T00:00:00Z",
      updated_at: "2026-08-27T00:00:00Z",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(baseOnboarding)))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...baseOnboarding,
            status: "ACCOUNT_PENDING",
            terms_completed: true,
            next_step: "ACCOUNT",
          }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            account: {
              id: "account-1",
              account_name: "나의 가상 투자계좌",
              operation_mode: "AUTO",
              initial_cash: "0",
              cash_balance: "0",
              status: "ACTIVE",
              selected_strategy_id: null,
              created_at: "2026-08-27T00:00:00Z",
            },
            created: true,
            required_deposit_amount: "10000000",
            onboarding: { ...baseOnboarding, status: "DEPOSIT_PENDING" },
          }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            deposit_id: "deposit-1",
            amount: "10000000",
            balance_after: "10000000",
            required_deposit_amount: "0",
            onboarding: { ...baseOnboarding, status: "READY" },
          }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...baseOnboarding,
            status: "COMPLETED",
            account_id: "account-1",
            terms_completed: true,
            account_exists: true,
            next_step: "PORTFOLIO",
            completed_at: "2026-08-27T00:00:01Z",
          }),
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    const result = await startInvestmentApi(
      "momentum",
      10_000_000,
      "AUTO",
      [{ term_code: "INVEST_PRODUCT_MOMENTUM", version: "v1", agreed: true }],
      "token-a",
    );

    expect(result.status).toBe("COMPLETED");
    expect(fetchMock).toHaveBeenCalledTimes(5);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/investment/onboardings",
      "/api/v1/investment/onboardings/onboarding-1/agreements",
      "/api/v1/investment/onboardings/onboarding-1/account",
      "/api/v1/investment/onboardings/onboarding-1/deposit",
      "/api/v1/investment/onboardings/onboarding-1/complete",
    ]);
    const depositBody = JSON.parse(
      String((fetchMock.mock.calls[3][1] as RequestInit).body),
    );
    expect(depositBody).toEqual({
      amount: 10_000_000,
      idempotency_key: "investment-onboarding-1-10000000",
    });
  });
});

describe("standalone account cash deposit API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("전략 정보 없이 계좌 id와 입금 요청만 전송한다", async () => {
    const response = {
      deposit_id: "deposit-1",
      account: {
        id: "account-1",
        account_name: "나의 가상 투자계좌",
        operation_mode: "SEMI_AUTO",
        initial_cash: "500000",
        cash_balance: "500000",
        invested_principal: "500000",
        status: "ACTIVE",
        selected_strategy_id: null,
        created_at: "2026-08-28T00:00:00Z",
      },
      amount: "500000",
      balance_after: "500000",
      status: "COMPLETED",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      depositAccountCashApi(
        "account-1",
        500_000,
        "cash-deposit-once",
        "token-a",
      ),
    ).resolves.toEqual(response);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/accounts/account-1/deposits",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          amount: 500_000,
          idempotency_key: "cash-deposit-once",
        }),
      }),
    );
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Headers).get("Authorization")).toBe(
      "Bearer token-a",
    );
    expect(String(init.body)).not.toContain("strategy");
  });
});
