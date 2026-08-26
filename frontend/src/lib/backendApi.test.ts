import { afterEach, describe, expect, it, vi } from 'vitest';
import { createStrategyRecommendationApi, type StrategyRecommendationResponse } from './backendApi';

const recommendation: StrategyRecommendationResponse = {
  recommendation_id: 'recommendation-1',
  assessment_id: 'assessment-1',
  primary: {
    strategy_id: 'value', rank: 1, score: 0.84, match_level: 'BEST',
    reason: '균형 성향과 잘 맞습니다.', caution: '회복까지 시간이 걸릴 수 있습니다.',
  },
  alternatives: [],
  model_version: 'strategy-recommender-v1',
  dataset_version: 'financial-8y-v1',
  recommendation_version: 'v1',
  created_at: '2026-08-27T00:00:00Z',
};

describe('strategy recommendation API', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('assessment id와 인증 토큰으로 실제 추천 생성 endpoint를 호출한다', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(recommendation), { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(createStrategyRecommendationApi('assessment-1', 'token-a')).resolves.toEqual(recommendation);
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/strategy-recommendations', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ assessment_id: 'assessment-1' }),
      headers: expect.any(Headers),
    }));
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer token-a');
  });
});
