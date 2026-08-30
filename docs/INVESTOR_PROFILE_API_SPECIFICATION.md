# 투자성향 점수 분석 API 명세서

## 1. 개요

사용자가 제출한 투자성향 설문 답변을 Backend가 검증하고 고정 점수표와 보수적 제한 규칙으로 분류한 뒤, 결과를 PostgreSQL에 저장하고 같은 HTTP 요청에서 구조화된 결과와 `assessment_id`를 반환한다.

- Base URL: `/api/v1`
- Content-Type: `application/json`
- 인증: `Authorization: Bearer <JWT>`
- 처리 방식: 단일 요청·응답 방식
- 데이터 저장: 원본 설문은 저장하지 않고 파생된 분석 성향과 재현 버전만 PostgreSQL에 저장
- 지원 설문 버전: `v1`

분류 과정에는 외부 AI 네트워크 호출이 없으며 `202 Accepted`, 작업 ID, polling, SSE, WebSocket은 사용하지 않는다.

## 2. Endpoint

### POST `/investor-profile/analyze`

투자성향 설문 답변을 분석·저장하고 완료된 결과를 반환한다. 현재 유효한 최신 `AI_PERSONALIZATION` 선택 약관 동의가 필요하다.

| 항목 | 값 |
| --- | --- |
| 전체 경로 | `POST /api/v1/investor-profile/analyze` |
| 인증 | 필요 |
| 성공 status | `200 OK` |
| 요청 body | `InvestorProfileAnalyzeRequest` |
| 응답 body | `InvestorProfileResponse` |

### GET `/investor-profile/me/latest`

인증 사용자의 가장 최근 저장 성향을 반환한다. 저장된 성향이 없으면 `404 INVESTOR_PROFILE_NOT_FOUND`다.

## 3. Request

### 3.1 Header

```http
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json
```

### 3.2 Body

```json
{
    "questionnaire_version": "v1",
  "answers": [
    {"question_id": "investment_experience", "option_id": "1_to_3_years"},
    {"question_id": "product_knowledge", "option_id": "basic"},
    {"question_id": "investment_horizon", "option_id": "3_to_5_years"},
    {"question_id": "investment_goal", "option_id": "retirement"},
    {"question_id": "loss_tolerance", "option_id": "loss_20_percent"},
    {"question_id": "risk_return_preference", "option_id": "balanced"},
    {"question_id": "investable_asset_ratio", "option_id": "10_to_30_percent"},
    {"question_id": "annual_income", "option_id": "30m_to_50m"}
  ]
}
```

### 3.3 Field 정의

| Field | Type | 필수 | 제약 |
| --- | --- | --- | --- |
| `questionnaire_version` | string | 예 | 현재 `v1`만 지원 |
| `answers` | array | 예 | `v1`의 8개 문항에 정확히 한 번씩 응답 |
| `answers[].question_id` | string | 예 | 아래 문항 ID 중 하나 |
| `answers[].option_id` | string | 예 | 해당 문항에 정의된 선택지 ID 중 하나 |

`answers` 배열의 순서는 결과에 영향을 주지 않는다. Backend가 `question_id` 기준으로 검증한 뒤 서버 카탈로그 순서로 정규화한다. 알 수 없는 field는 허용하지 않는다.

다음 경우 `400 INVALID_INVESTOR_ANSWERS`를 반환한다.

- 문항 누락
- 정의되지 않은 문항 추가
- 동일 문항 중복 제출
- 문항과 맞지 않는 선택지 제출

### 3.4 v1 문항 및 선택지

#### Q1. 투자 경험

`question_id`: `investment_experience`

| `option_id` | 표시 문구 |
| --- | --- |
| `none` | 처음이에요 |
| `under_1_year` | 1년 미만 |
| `1_to_3_years` | 1~3년 |
| `3_to_5_years` | 3~5년 |
| `over_5_years` | 5년 이상 |

#### Q2. 금융상품 이해도

`question_id`: `product_knowledge`

| `option_id` | 표시 문구 |
| --- | --- |
| `very_low` | 거의 몰라요 |
| `basic` | 기본적인 내용은 알아요 |
| `intermediate` | 어느 정도 이해하고 있어요 |
| `advanced` | 다양한 투자상품을 잘 이해하고 있어요 |

#### Q3. 투자 기간

`question_id`: `investment_horizon`

| `option_id` | 표시 문구 |
| --- | --- |
| `under_1_year` | 1년 미만 |
| `1_to_3_years` | 1~3년 |
| `3_to_5_years` | 3~5년 |
| `over_5_years` | 5년 이상 |

#### Q4. 투자 목적

`question_id`: `investment_goal`

| `option_id` | 표시 문구 |
| --- | --- |
| `living_expenses` | 생활에 필요한 자금 마련 |
| `major_purchase` | 주택·결혼 등 목돈 마련 |
| `retirement` | 노후 준비 |
| `surplus_management` | 여유자금 운용 |
| `long_term_growth` | 장기적인 자산 증식 |

#### Q5. 감당 가능한 손실

`question_id`: `loss_tolerance`

| `option_id` | 표시 문구 |
| --- | --- |
| `no_loss` | 원금 손실을 원하지 않아요 |
| `loss_10_percent` | 10% 정도의 손실까지 괜찮아요 |
| `loss_20_percent` | 20% 정도의 손실까지 괜찮아요 |
| `loss_30_percent` | 30% 정도의 손실까지 괜찮아요 |
| `loss_over_30_percent` | 더 큰 손실도 감수할 수 있어요 |

#### Q6. 수익·안정성 선호

`question_id`: `risk_return_preference`

| `option_id` | 표시 문구 |
| --- | --- |
| `principal_preservation` | 원금 보존이 가장 중요해요 |
| `stability` | 안정성을 더 중요하게 생각해요 |
| `balanced` | 안정성과 수익을 비슷하게 생각해요 |
| `return` | 수익을 더 중요하게 생각해요 |
| `high_return` | 높은 수익을 위해 큰 변동도 감수할 수 있어요 |

#### Q7. 투자 가능 자산 비중

`question_id`: `investable_asset_ratio`

| `option_id` | 표시 문구 |
| --- | --- |
| `under_10_percent` | 10% 미만 |
| `10_to_30_percent` | 10~30% |
| `30_to_50_percent` | 30~50% |
| `50_to_70_percent` | 50~70% |
| `over_70_percent` | 70% 이상 |

#### Q8. 연간 소득

`question_id`: `annual_income`

| `option_id` | 표시 문구 |
| --- | --- |
| `under_10m` | 1천만원 미만 |
| `10m_to_30m` | 1천만원 이상 ~ 3천만원 미만 |
| `30m_to_50m` | 3천만원 이상 ~ 5천만원 미만 |
| `50m_to_80m` | 5천만원 이상 ~ 8천만원 미만 |
| `over_80m` | 8천만원 이상 |

### 3.5 점수 및 분류 기준

| 문항 | 선택지 점수 | 최대점수 |
| --- | --- | ---: |
| 투자 경험 | 처음 0 / 1년 미만 2 / 1~3년 5 / 3~5년 7 / 5년 이상 10 | 10 |
| 금융상품 이해도 | 거의 모름 0 / 기본 3 / 어느 정도 이해 7 / 매우 잘 이해 10 | 10 |
| 투자 기간 | 1년 미만 0 / 1~3년 4 / 3~5년 8 / 5년 이상 12 | 12 |
| 투자 목적 | 생활자금 0 / 목돈 마련 2 / 노후 준비 4 / 여유자금 6 / 장기 자산 증식 8 | 8 |
| 감당 가능한 손실 | 손실 불가 0 / 10% 6 / 20% 12 / 30% 18 / 30% 초과 24 | 24 |
| 수익·안정성 선호 | 원금 보존 0 / 안정성 6 / 균형 12 / 수익 18 / 고수익·고변동 24 | 24 |
| 투자 가능 자산 비중 | 10% 미만 7 / 10~30% 5 / 30~50% 3 / 50~70% 1 / 70% 이상 0 | 7 |
| 연간 소득 | 1천만원 미만 0 / 1~3천만원 1 / 3~5천만원 2 / 5~8천만원 3 / 8천만원 이상 5 | 5 |

최종 점수 구간은 `0~19 안정추구형`, `20~39 안정투자형`, `40~59 중립투자형`, `60~79 성장추구형`, `80~100 공격투자형`이다.

합산 결과에는 다음 보수적 제한 규칙을 적용한다. 제한 후 `risk_score`도 최종 유형의 점수 구간에 맞게 조정하므로 점수와 유형이 서로 어긋나지 않는다.

- 원금 손실 불가 또는 원금 보존 최우선: 최대 19점
- 손실 감내도 10% 또는 안정성 우선: 최대 39점
- 공격투자형: 손실 감내도 30% 이상과 고수익·고변동 선호를 모두 충족해야 함
- 금융상품 이해도가 가장 낮으면 최대 79점
- 생활자금 목적 또는 금융자산의 70% 이상을 투자하면 한 단계 하향

## 4. Response

### 4.1 성공 응답

Status: `200 OK`

```json
{
  "assessment_id": "6118bc91-39b0-46f1-b726-7123e254437d",
  "profile_type": "중립투자형",
  "risk_score": 51,
  "tendency_line": "안정성과 수익의 균형을 중요하게 생각하는 투자자예요.",
  "description": "일정 수준의 변동은 감수하지만 과도한 위험은 피하는 성향입니다.",
  "traits": {
    "stability": 3,
    "return_seeking": 3,
    "horizon": 4
  },
  "analysis_summary": [
    "투자성향 점수는 100점 만점에 51점입니다.",
    "감당 가능한 손실은 '20% 정도의 손실까지 괜찮아요'로 응답했습니다.",
    "수익과 안정성 선호는 '안정성과 수익을 비슷하게 생각해요'로 응답했습니다.",
    "예상 투자 기간은 '3~5년'입니다."
  ],
  "questionnaire_version": "v1",
  "analysis_version": "v2",
  "model_version": "risk-score-v1",
  "created_at": "2026-08-24T15:00:00+09:00"
}
```

### 4.2 Field 정의

| Field | Type | 제약/의미 |
| --- | --- | --- |
| `assessment_id` | UUID | 저장된 분석 성향 식별자 |
| `profile_type` | string | 정의된 5개 투자유형 중 하나 |
| `risk_score` | integer 또는 null | 최종 위험 점수, 0~100. 점수 도입 전 v1 기록은 `null` |
| `tendency_line` | string | 결과 화면용 한 줄 설명, 1~200자 |
| `description` | string | 투자성향 상세 설명, 1~500자 |
| `traits.stability` | integer | 안정성 선호, 1~5 |
| `traits.return_seeking` | integer | 수익추구 성향, 1~5 |
| `traits.horizon` | integer | 투자기간 성향, 1~5 |
| `analysis_summary` | string array | 응답에 근거한 분석 요약, 1~5개 |
| `questionnaire_version` | string | 요청에 사용된 설문 버전 |
| `analysis_version` | string | Backend 분석 응답 계약 버전. 신규 분석은 `v2`, 기존 기록은 `v1` |
| `model_version` | string | 분류 로직 재현 버전. 신규 분석은 `risk-score-v1` |
| `created_at` | datetime | 분석 성향 저장 시각 |

허용되는 `profile_type`:

- `안정추구형`
- `안정투자형`
- `중립투자형`
- `성장추구형`
- `공격투자형`

Backend는 검증된 선택지 ID만 점수화하며, 점수 범위와 허용 유형은 코드 및 DB 제약으로 검증한다.

## 5. 오류 응답

공통 형식:

```json
{
  "code": "INVALID_INVESTOR_ANSWERS",
  "message": "모든 설문 문항에 정확히 한 번씩 답변해야 합니다."
}
```

| HTTP | `code` | 발생 조건 |
| --- | --- | --- |
| 400 | `INVALID_QUESTIONNAIRE_VERSION` | 지원하지 않는 설문 버전 |
| 400 | `INVALID_INVESTOR_ANSWERS` | 문항 누락·추가·중복 또는 잘못된 선택지 |
| 401 | `AUTHENTICATION_REQUIRED` | Authorization header 누락 |
| 401 | `INVALID_TOKEN` | 만료되었거나 유효하지 않은 JWT |
| 403 | `AI_PERSONALIZATION_CONSENT_REQUIRED` | AI 개인화 선택 약관 미동의 |
| 404 | `INVESTOR_PROFILE_NOT_FOUND` | 최신 저장 성향 없음 |
| 422 | FastAPI validation error | JSON 형식 또는 request field type/길이 오류 |
오류 응답에는 사용자의 설문 원문이나 내부 점수 계산 상세를 포함하지 않는다.

## 6. 호출 예시

```bash
curl --request POST 'http://localhost:8000/api/v1/investor-profile/analyze' \
  --header 'Authorization: Bearer <access-token>' \
  --header 'Content-Type: application/json' \
  --data '{
    "questionnaire_version": "v1",
    "answers": [
      {"question_id":"investment_experience","option_id":"1_to_3_years"},
      {"question_id":"product_knowledge","option_id":"basic"},
      {"question_id":"investment_horizon","option_id":"3_to_5_years"},
      {"question_id":"investment_goal","option_id":"retirement"},
      {"question_id":"loss_tolerance","option_id":"loss_20_percent"},
      {"question_id":"risk_return_preference","option_id":"balanced"},
      {"question_id":"investable_asset_ratio","option_id":"10_to_30_percent"},
      {"question_id":"annual_income","option_id":"30m_to_50m"}
    ]
  }'
```

## 7. Backend 환경변수

투자성향 점수 계산에는 Azure OpenAI 또는 별도 분석 환경변수가 필요하지 않다. 점수표와 보수적 제한 규칙은 `risk-score-v1` 코드 버전으로 관리한다.

## 8. 처리 및 보안 경계

1. client가 보낸 질문 문구는 받지 않는다.
2. Backend가 `question_id`와 `option_id`를 서버 카탈로그의 문구로 변환한다.
3. 검증된 선택지 ID에 서버의 고정 점수표를 적용한다.
4. 원본 설문은 영속화하지 않고 점수·분류된 성향과 재현 버전만 저장한다.
5. 저장 전에 현재 발효된 최신 `AI_PERSONALIZATION` 약관 version에 대한 동의를 확인한다.
6. 사용자 금융정보를 로그에 기록하지 않는다.

현재 구현은 투자성향 안내용이다. 실제 금융상품 적합성·적정성 판단에 사용하려면 별도로 승인된 고정 분류 기준과 준법 검토가 필요하다.
