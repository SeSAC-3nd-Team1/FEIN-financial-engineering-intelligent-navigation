import { describe, expect, it } from 'vitest';
import { mapInvestorProfileResponse } from './investorProfile';

describe('mapInvestorProfileResponse', () => {
  it.each(['안정추구형', '안정투자형', '중립투자형', '성장추구형', '공격투자형'] as const)(
    '백엔드 profile_type %s를 화면 유형으로 보존한다',
    (profileType) => {
      const result = mapInvestorProfileResponse({
        assessment_id: 'assessment-1',
        questionnaire_version: 'v1',
        analysis_version: 'v1',
        risk_score: null,
        profile_type: profileType,
        tendency_line: '성향 설명',
        description: '상세 설명',
        traits: { stability: 3, return_seeking: 3, horizon: 3 },
        analysis_summary: [],
        model_version: 'investor-profile-v1',
        created_at: '2026-08-30T00:00:00Z',
      });

      expect(result.type).toBe(profileType);
    },
  );
});
