# 가상투자 시작 Backend API 명세

## 범위

실제 증권사 계좌를 개설하거나 연결하지 않는다. 로그인 사용자에게 `AUTO`, `SEMI_AUTO` 운용방식별
내부 `virtual_accounts`를 하나씩 생성하거나 재사용하며, 투자 약관 동의와 선택한 전략·금액·운용방식을
`investment_onboardings`에 각각 저장한다. 가상계좌번호는 발급하거나 노출하지 않는다.

회원가입에서 `phone_verified_at`, `email_verified_at`이 기록된 사용자를 본인확인 완료 사용자로 본다.
별도의 가짜 OTP나 외부 증권사 인증 API는 제공하지 않는다.

## 상태 흐름

```text
TERMS_PENDING -> ACCOUNT_PENDING -> DEPOSIT_PENDING -> READY -> COMPLETED
```

| 상태 | `next_step` | 의미 |
| --- | --- | --- |
| `TERMS_PENDING` | `TERMS` | 최신 투자 필수 약관 동의 필요 |
| `ACCOUNT_PENDING` | `ACCOUNT` | 가상계좌 생성 또는 기존 계좌 재사용 필요 |
| `DEPOSIT_PENDING` | `DEPOSIT` | 투자 예정 금액 대비 부족한 가상 투자금 입금 필요 |
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

`operation_mode`는 `AUTO`, `SEMI_AUTO`만 허용한다. 사용자·운용방식당 한 행을 유지하며, 완료 후 투자
조건을 바꾸면 같은 운용방식의 약관·계좌·잔액 상태에 따라 진행 상태를 다시 계산한다.

### GET `/api/v1/investment/onboardings/me/current?operation_mode=AUTO`

운용방식을 생략하면 하위 호환을 위해 `SEMI_AUTO`를 조회한다. 두 운용방식 상태를 한 번에 조회하려면
`GET /api/v1/investment/onboardings/me`를 사용한다. 온보딩이 없는 운용방식은 목록 응답에 포함되지 않는다.

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

같은 운용방식의 계좌가 없으면 `initial_cash=0`, `cash_balance=0`인 가상계좌를 생성하고
`created=true`를 반환한다. 계좌 준비만으로 현금원장은 만들지 않으며 응답의
`required_deposit_amount`와 `next_step=DEPOSIT`으로 필요한 입금액을 알린다.

이미 같은 운용방식의 사용자 계좌가 있으면 새 계좌를 만들지 않고 해당 계좌와 `created=false`를
반환한다. 다른 운용방식의 계좌는 재사용하지 않는다. 기존 계좌의 잔액, 계좌명, 포지션과 원장은
변경하거나 초기화하지 않으며 현재 잔액과 투자 예정 금액의 차이만 부족분으로 계산한다.
외부 계좌 식별자, 증권사 credential, OTP는 받지 않는다.

### POST `/api/v1/investment/onboardings/{id}/deposit`

```json
{
  "amount": 1000000,
  "idempotency_key": "5ce6b4e0-79f6-4f55-9405-75ff5617c66e"
}
```

`amount`는 요청 시점의 `max(0, investment_amount - cash_balance)`와 정확히 같아야 한다. 일부 입금,
초과 입금, 이미 잔액이 충분한 계좌의 추가 입금은 허용하지 않는다. 성공하면 계좌 행을 잠근 하나의
transaction에서 `account_deposits`, `virtual_accounts.cash_balance`, `cash_ledger(DEPOSIT)`,
온보딩 `READY`를 함께 반영한다.

같은 계좌와 `idempotency_key`로 동일 요청을 재전송하면 기존 성공 결과를 반환한다. 같은 키를 다른
금액이나 온보딩에 사용하면 `409 DEPOSIT_IDEMPOTENCY_CONFLICT`, 현재 부족분과 다르면
`409 INVALID_DEPOSIT_AMOUNT`, 입금이 필요하지 않으면 `409 DEPOSIT_NOT_REQUIRED`다.

### POST `/api/v1/investment/onboardings/{id}/complete`

최신 약관, 계좌 소유권·활성 상태, 가상현금 잔액, 전략 활성 상태를 다시 검증한다. 성공하면 계좌의
`selected_strategy_id`, 온보딩 `COMPLETED` 상태와 사용자의 `active_operation_mode`를 하나의
transaction으로 저장한다. 새 운용방식의 최초 완료는 해당 계좌를 현재 활성 계좌로 선택하지만,
이미 완료된 요청의 재전송은 사용자가 이후 명시적으로 바꾼 활성 방식을 되돌리지 않는다.

입금이 완료되지 않아 현재 현금이 투자 예정 금액보다 작으면 `409 INSUFFICIENT_VIRTUAL_CASH`를
반환한다. 다른 운용방식 계좌의 잔액·포지션·거래내역은 변경하지 않는다.
