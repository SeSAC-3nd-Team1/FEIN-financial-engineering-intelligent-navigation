# AI 전략 추천 API 명세서

## 1. 개요

저장된 투자성향과 활성 전략 catalog를 최근 8년 데이터로 학습된 Azure OpenAI 추천 deployment에 전달하고, 검증된 전략 순위를 PostgreSQL에 저장한다. 원본 투자성향 설문은 추천 모델에 다시 전달하지 않는다.

- Base URL: `/api/v1`
- 인증: Bearer JWT 필수
- 선행 조건: 사용자의 현재 유효한 최신 `AI_PERSONALIZATION` 약관 동의와 저장된 투자성향
- 추천 모델 데이터셋 기본 버전: `financial-8y-v1`
- 멱등 기준: `assessment_id + model_version + prompt_version + strategy_catalog_version + dataset_version`

## 2. POST `/strategy-recommendations`

### Request

```json
{"assessment_id":"6118bc91-39b0-46f1-b726-7123e254437d"}
```

Backend는 해당 `assessment_id`가 인증 사용자 소유인지 확인한다. 저장된 성향의 `profile_type`, `stability`, `return_seeking`, `horizon`, `description`과 DB의 활성 전략 ID·이름·위험등급·리밸런싱 주기만 추천 모델에 전달한다.

`AI_PERSONALIZATION` 동의는 `effective_at <= now()`인 약관 중 가장 최근에 발효된 version을 기준으로 확인한다. 과거 version에 동의했더라도 현재 version에 동의하지 않았다면 추천을 요청할 수 없다.

### Response

Status: `201 Created`

```json
{
  "recommendation_id": "bd189cb0-91b2-467e-90de-a6bf03189818",
  "assessment_id": "6118bc91-39b0-46f1-b726-7123e254437d",
  "primary": {
    "strategy_id": "value",
    "rank": 1,
    "score": 0.84,
    "match_level": "BEST",
    "reason": "안정성과 수익의 균형을 추구하는 성향과 적합합니다.",
    "caution": "가치 회복까지 시간이 걸릴 수 있습니다."
  },
  "alternatives": [],
  "model_version": "strategy-recommender-v1",
  "dataset_version": "financial-8y-v1",
  "recommendation_version": "v1",
  "created_at": "2026-08-24T15:01:00+09:00"
}
```

같은 멱등 기준의 결과가 이미 있으면 모델을 재호출하지 않고 저장된 추천을 반환한다. 응답 status는 동일하게 `201`이다.

## 3. GET `/strategy-recommendations/me/latest`

인증 사용자의 가장 최근 추천과 순위 항목을 반환한다. 저장된 추천이 없으면 `404 STRATEGY_RECOMMENDATION_NOT_FOUND`다.

## 4. 검증 규칙

- 활성 전략 중 최대 3개를 정확히 한 번씩 추천한다.
- `rank`는 1부터 연속되고 중복될 수 없다.
- `score`는 0~1이고 순위가 내려갈수록 증가할 수 없다.
- `score`는 예상수익률이나 수익 확률이 아니라 성향 적합도다.
- 구조화 출력, 전략 ID 또는 순위가 유효하지 않으면 결과를 저장하지 않는다.
- 원본 설문, API key, provider 원문 오류는 응답이나 로그에 포함하지 않는다.

## 5. 오류

| HTTP | code | 조건 |
| --- | --- | --- |
| 401 | `AUTHENTICATION_REQUIRED`, `INVALID_TOKEN` | 인증 실패 |
| 403 | `AI_PERSONALIZATION_CONSENT_REQUIRED` | AI 개인화 동의 없음 |
| 404 | `INVESTOR_PROFILE_NOT_FOUND` | 없거나 다른 사용자 소유 성향 |
| 404 | `STRATEGY_RECOMMENDATION_NOT_FOUND` | 최신 추천 없음 |
| 502 | `AI_RECOMMENDATION_UNAVAILABLE` | provider 연결·4xx 오류 |
| 502 | `AI_INVALID_RECOMMENDATION` | JSON 또는 추천 의미 검증 실패 |
| 503 | `AI_RECOMMENDATION_NOT_CONFIGURED` | 필수 설정 누락 |
| 503 | `AI_RECOMMENDATION_UNAVAILABLE` | provider 429·5xx |
| 503 | `STRATEGY_CATALOG_UNAVAILABLE` | 활성 전략 없음 |
| 504 | `AI_RECOMMENDATION_TIMEOUT` | 추론 timeout |

## 6. 환경변수

| 환경변수 | 기본값 |
| --- | --- |
| `AZURE_OPENAI_RECOMMENDATION_DEPLOYMENT` | 없음 |
| `AI_RECOMMENDATION_TIMEOUT_SECONDS` | `15` |
| `AI_RECOMMENDATION_MODEL_VERSION` | `strategy-recommender-v1` |
| `AI_RECOMMENDATION_PROMPT_VERSION` | `v1` |
| `AI_RECOMMENDATION_DATASET_VERSION` | `financial-8y-v1` |
| `STRATEGY_CATALOG_VERSION` | `v1` |
