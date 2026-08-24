# 가상투자 시작 Backend API 명세

## 범위

실제 증권사 계좌를 개설하거나 연결하지 않는다. 로그인 사용자당 하나의 내부
`virtual_accounts`를 생성하거나 기존 계좌를 재사용하며, 투자 약관 동의와 선택한 전략·금액·운용방식을
`investment_onboardings`에 저장한다.

회원가입에서 `phone_verified_at`, `email_verified_at`이 기록된 사용자를 본인확인 완료 사용자로 본다.
별도의 가짜 OTP나 외부 증권사 인증 API는 제공하지 않는다.

## 상태 흐름

```text
TERMS_PENDING -> ACCOUNT_PENDING -> READY -> COMPLETED
```

| 상태 | `next_step` | 의미 |
| --- | --- | --- |
| `TERMS_PENDING` | `TERMS` | 최신 투자 필수 약관 동의 필요 |
| `ACCOUNT_PENDING` | `ACCOUNT` | 가상계좌 생성 또는 기존 계좌 재사용 필요 |
| `READY` | `CONFIRM` | 투자 조건 최종 확인 가능 |
| `COMPLETED` | `PORTFOLIO` | 투자 시작 완료 |

새 약관 version이 효력을 시작하면 저장된 상태가 `COMPLETED`여도 응답의 유효 상태는
`TERMS_PENDING`이 된다. 계좌 준비와 완료 시에도 최신 동의를 다시 검증한다.

## Endpoint

모든 API는 Bearer JWT 인증이 필요하다.

### GET `/api/v1/investment/terms?strategy_id=low`

전략별 상품설명서 한 건과 공통 필수 약관 세 건의 현재 유효한 최신 version을 반환한다.
필수 catalog가 하나라도 없거나 선택 사항으로 잘못 등록되어 있으면 `503 TERMS_CATALOG_UNAVAILABLE`이다.

### POST `/api/v1/investment/onboardings`

```json
{
  "strategy_id": "low",
  "investment_amount": 1000000,
  "operation_mode": "AUTO"
}
```

`operation_mode`는 `AUTO`, `SEMI_AUTO`만 허용한다. 사용자당 한 행을 유지하며, 완료 후 투자 조건을
바꾸면 최신 약관·계좌 상태에 따라 진행 상태를 다시 계산한다.

### GET `/api/v1/investment/onboardings/me/current`

```json
{
  "id": "7efb973f-7514-4955-9837-c60975efb4f8",
  "strategy_id": "low",
  "investment_amount": "1000000.00",
  "operation_mode": "AUTO",
  "status": "ACCOUNT_PENDING",
  "account_id": null,
  "terms_completed": true,
  "account_exists": false,
  "next_step": "ACCOUNT",
  "completed_at": null,
  "created_at": "2026-08-24T12:00:00Z",
  "updated_at": "2026-08-24T12:00:00Z"
}
```

### POST `/api/v1/investment/onboardings/{id}/agreements`

현재 전략에 필요한 최신 약관만 받는다. 필수 약관 누락·거절은
`400 INVESTMENT_TERMS_NOT_AGREED`, 과거 또는 다른 전략의 약관은 `400 INVALID_TERM_VERSION`이다.
동의 시각, 요청 IP, User-Agent를 `user_agreements`에 감사 정보로 저장한다.

### POST `/api/v1/investment/onboardings/{id}/account`

```json
{"account_name":"나의 가상 투자계좌"}
```

계좌가 없으면 `investment_amount`를 `initial_cash`, `cash_balance`, 최초 `INITIAL_DEPOSIT`의
`amount`, `balance_after`로 사용해 가상계좌와 초기 현금원장을 같은 transaction에서 생성하고
`created=true`를 반환한다.

이미 사용자 계좌가 있으면 새 계좌를 만들지 않고 해당 계좌와 `created=false`를 반환한다. 기존 계좌의
잔액, 계좌명, 포지션과 원장은 변경하거나 초기화하지 않는다. 새로 선택한 투자 금액을 추가 입금하지도
않으며, 완료 단계에서 현재 `cash_balance`가 선택 금액 이상인지만 검증한다.
외부 계좌 식별자, 증권사 credential, OTP는 받지 않는다.

### POST `/api/v1/investment/onboardings/{id}/complete`

최신 약관, 계좌 소유권·활성 상태, 가상현금 잔액, 전략 활성 상태를 다시 검증한다. 성공하면 계좌의
`selected_strategy_id`와 온보딩 `COMPLETED` 상태를 하나의 transaction으로 저장한다.

신규 계좌의 시작 자금은 투자 예정 금액과 같다. 기존 계좌를 재사용할 때 예정 금액이 현재 현금보다
크면 `409 INSUFFICIENT_VIRTUAL_CASH`를 반환한다.
