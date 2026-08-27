import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createStrategyRecommendationApi,
  getLatestModelRecommendationsApi,
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
  model_version: "price-momentum-v1",
  data_version: "algorithm-ohlcv-v2",
  status: "ready",
  market_regime: "neutral",
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
