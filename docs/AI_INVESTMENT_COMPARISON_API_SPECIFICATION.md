# AI 자동투자와 내 투자 비교 API

## 목적

인증 사용자의 `AUTO` 계좌와 `SEMI_AUTO` 계좌 성과를 같은 기간과 기준일로 비교하고,
Backend가 검증한 지표를 AI 모델이 프론트 표시용 한국어 문구로 해설한다.

API는 `GET /api/v1/portfolio/comparison?period=3M`이다. `period`는 `1M`, `3M`, `1Y`,
`ALL`을 지원한다. 프론트는 계좌 ID를 전달하지 않는다. Backend가 인증 사용자 소유의 두
운용방식 계좌를 조회하므로 다른 사용자의 계좌를 비교 대상으로 주입할 수 없다.

## 계산 원칙

- 원천 데이터는 장 마감 후 저장된 `portfolio_snapshots.total_assets`다.
- 선택 기간 안에서 두 계좌에 모두 snapshot이 존재하는 날짜만 사용한다.
- 첫 공통 관측일의 각 계좌 자산을 각각 0% 기준으로 정규화한다.
- 계좌별 수익률은 `(현재 자산 / 기준 자산 - 1) * 100`이며 소수 둘째 자리까지 반환한다.
- `return_rate_gap`은 `AI 자동투자 수익률 - 내 투자 수익률`이다.
- `leader`는 수익률 격차 기준 `AI_AUTO`, `MY_INVESTMENT`, `TIE` 중 하나다.
- `asset_gap`은 최신 공통 관측일의 원화 자산 차이다. 초기 투자금이 다르면 성과 우열로
  해석하지 않으며 AI prompt에도 이 제한을 명시한다.
- 공통 관측일이 2개 미만이거나 기준 자산이 0원이면 합성 데이터를 만들지 않고
  `comparison_status="INSUFFICIENT_DATA"`를 반환하며 AI를 호출하지 않는다.

두 계좌 중 하나라도 없으면 `409 COMPARISON_ACCOUNTS_REQUIRED`를 반환한다.

## 응답 예시

```json
{
  "comparison_status": "AVAILABLE",
  "calculation_version": "portfolio-comparison-v1",
  "period": "3M",
  "baseline_date": "2026-06-01",
  "as_of": "2026-08-25",
  "observation_count": 58,
  "accounts": {
    "ai_auto": {
      "account_id": "0dc87502-73b2-4c4c-bfc7-1644b9b21659",
      "account_name": "AI 자동투자",
      "operation_mode": "AUTO",
      "strategy_id": "low",
      "baseline_assets": "1000000.00",
      "current_assets": "1100000.00",
      "return_rate": "10.00"
    },
    "my_investment": {
      "account_id": "41faf217-3d39-432f-bb9f-a52dd70dfe20",
      "account_name": "내 투자",
      "operation_mode": "SEMI_AUTO",
      "strategy_id": "balanced",
      "baseline_assets": "2000000.00",
      "current_assets": "2100000.00",
      "return_rate": "5.00"
    }
  },
  "metrics": {
    "return_rate_gap": "5.00",
    "asset_gap": "-1000000.00",
    "leader": "AI_AUTO"
  },
  "series": [
    {
      "date": "2026-06-01",
      "ai_auto_return_rate": "0.00",
      "my_investment_return_rate": "0.00",
      "return_rate_gap": "0.00"
    }
  ],
  "ai_analysis": {
    "status": "AVAILABLE",
    "headline": "AI 자동투자 수익률이 비교 기간에 앞섰습니다.",
    "summary": "공통 관측 기간 동안 5.00%p의 수익률 격차가 확인됐습니다.",
    "key_points": ["AI 자동투자 +10.00%", "내 투자 +5.00%"],
    "caution": "과거 가상투자 결과이며 미래 수익을 보장하지 않습니다.",
    "model_version": "portfolio-comparison-v1",
    "generated_at": "2026-08-26T05:00:00Z"
  }
}
```

`comparison_status="INSUFFICIENT_DATA"`일 때 `metrics`는 `null`, `series`는 빈 배열이다.
계좌별 최신 snapshot이 있으면 `current_assets`는 제공하지만 기준 자산과 수익률은 `null`이다.

## AI 경계와 부분 실패

모델 입력에는 기간, 공통 기준일, 관측 수, 두 운용방식의 전략 ID·기준/현재 자산·수익률,
서버 산출 격차와 leader만 포함한다. 사용자 ID, 계좌 ID, 계좌명은 전송하지 않는다. 모델은
숫자를 계산하지 않고 `headline`, `summary`, `key_points`, `caution`만 구조화 JSON으로 생성한다.

모델 설정 누락, timeout, 429/5xx, 네트워크 오류, 거부 응답 또는 schema 오류는 비교 숫자 API를
실패시키지 않는다. 이 경우 `comparison_status`와 서버 계산 결과는 유지하고
`ai_analysis.status="UNAVAILABLE"` 및 안전한 안내 문구를 반환한다.

## 환경변수

| 환경변수 | 기본값 | 설명 |
| --- | --- | --- |
| `AZURE_OPENAI_ENDPOINT` | 없음 | 공용 Azure OpenAI endpoint |
| `AZURE_OPENAI_API_KEY` | 없음 | 공용 Azure OpenAI API key |
| `AZURE_OPENAI_COMPARISON_DEPLOYMENT` | 없음 | 투자 비교 모델 deployment |
| `AZURE_OPENAI_API_VERSION` | `2024-10-21` | Azure OpenAI API version |
| `AI_COMPARISON_TIMEOUT_SECONDS` | `15` | 모델 호출 제한시간 |
| `AI_COMPARISON_MODEL_VERSION` | `portfolio-comparison-v1` | 프론트 표시 모델 버전 |
