# AI 리밸런싱 제안 계약

## 목적과 현재 상태

포트폴리오 홈의 리밸런싱 제안, 제안 이유와 “왜 지금인가” 문구를 AI 모델 응답에 기반해
제공한다. 모델 deployment는 아직 준비되지 않았지만 Backend의 client 인터페이스, 구조화 출력,
검증과 부분 실패 계약은 구현되어 있다. 실제 모델 연결 시 환경변수만 설정하며 API 응답 구조는
변경하지 않는다.

API는 `GET /api/v1/portfolio/home?account_id=...`이다. 별도 AI endpoint를 프론트에 노출하지
않으며 인증 사용자와 계좌 ID만으로 Backend가 현재 포트폴리오를 구성한다.

## 처리 흐름

1. Backend가 계좌 소유권, 현재가, 보유수량, 현금과 적용 시점의 전략 목표 비중을 조회한다.
2. 목표 비중 합계가 정확히 100%인지 검증하고 종목별 BUY/SELL, 비중 차이와 금액 후보를 계산한다.
3. 모델에는 사용자·계좌 식별자를 제외한 운용방식, 전략 ID, 총자산, 현금, 가격 기준시각과
   검증된 후보만 전달한다.
4. 모델은 최대 5개 후보를 선택해 우선순위, 제안 이유와 `why_now`를 구조화 JSON으로 반환한다.
5. Backend가 종목·현재/목표/차이 비중·방향·금액이 원래 후보와 정확히 같은지 다시 검증한다.
6. 검증된 결과만 `source="AI"`로 프론트에 반환한다.

AI는 새로운 종목이나 금액을 만드는 권한이 없다. 숫자 계산은 Backend가 담당하고 AI는 검증된
후보의 선택, 순서와 설명을 담당한다. 입력에 없는 뉴스·가격·재무 사실 및 미래 수익률 추측은
prompt에서 금지한다.

## 모델 구조화 출력

```json
{
  "summary": "목표 비중과 현재 비중의 차이가 커져 점검이 필요합니다.",
  "proposals": [
    {
      "stock_code": "005930",
      "priority": 1,
      "current_weight": "20.00",
      "target_weight": "15.00",
      "weight_diff": "5.00",
      "action": "SELL",
      "recommended_amount": "50000.00",
      "reason": "전략 목표보다 보유 비중이 높습니다.",
      "why_now": "현재 목표 비중과의 차이가 5%p로 확대됐습니다."
    }
  ]
}
```

`priority`는 1부터 연속되고 종목은 중복될 수 없다. 모든 문구는 1~500자이며 제안은 최대 5개다.
JSON Schema와 Pydantic 검증을 모두 통과해야 한다.

## 프론트 응답

```json
{
  "rebalancing_insight": {
    "status": "AVAILABLE",
    "summary": "목표 비중과 현재 비중의 차이가 커져 점검이 필요합니다.",
    "model_version": "rebalancing-v1",
    "generated_at": "2026-08-25T09:00:00Z"
  },
  "rebalancing_proposals": [
    {
      "stock_code": "005930",
      "stock_name": "삼성전자",
      "current_weight": "20.00",
      "target_weight": "15.00",
      "weight_diff": "5.00",
      "action": "SELL",
      "recommended_amount": "50000.00",
      "priority": 1,
      "reason": "전략 목표보다 보유 비중이 높습니다.",
      "why_now": "현재 목표 비중과의 차이가 5%p로 확대됐습니다.",
      "source": "AI"
    }
  ]
}
```

상태 계약:

- `AVAILABLE`: 검증된 AI 결과가 있으며 제안 목록을 표시한다.
- `NOT_NEEDED`: 전략 목표 비중과 현재 비중이 일치하며 모델을 호출하지 않는다.
- `UNAVAILABLE`: 목표 비중 또는 모델을 사용할 수 없다. 홈의 계좌·자산·종목 데이터는 계속 표시한다.

모델 설정 누락, timeout, 429/5xx, 네트워크 오류, 거부 응답, JSON/schema 오류와 후보 불일치는
모두 AI 영역의 `UNAVAILABLE`로 격리한다. provider 원문과 credential은 응답·로그에 포함하지 않는다.

## 환경변수

| 환경변수 | 기본값 | 설명 |
| --- | --- | --- |
| `AZURE_OPENAI_ENDPOINT` | 없음 | 공용 Azure OpenAI endpoint |
| `AZURE_OPENAI_API_KEY` | 없음 | 공용 Azure OpenAI API key |
| `AZURE_OPENAI_REBALANCING_DEPLOYMENT` | 없음 | 리밸런싱 모델 deployment |
| `AZURE_OPENAI_API_VERSION` | `2024-10-21` | Azure OpenAI API version |
| `AI_REBALANCING_TIMEOUT_SECONDS` | `15` | 모델 호출 제한시간 |
| `AI_REBALANCING_MODEL_VERSION` | `rebalancing-v1` | 프론트 응답에 표시할 모델 버전 |

모델 결과를 DB에 저장하는 기능이 추가되면 모델·prompt·입력 snapshot과 함께 영속화한다. 현재 응답은 조회 시점에 생성되며
`rebalancing_decisions`에는 사용자가 수락 또는 보류한 서버 검증 숫자만 저장한다.
