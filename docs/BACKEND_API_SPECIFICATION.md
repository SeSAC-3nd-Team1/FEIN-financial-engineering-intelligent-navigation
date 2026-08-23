# Backend API 명세서

Base URL: `/api/v1` · Content-Type: `application/json` · 인증: `Authorization: Bearer <JWT>`

공통 오류:

```json
{"code":"INSUFFICIENT_CASH","message":"주문 가능한 현금이 부족합니다."}
```

## Endpoint 목록

| 기능 | Method | Endpoint | 인증 | 주요 status | 관련 화면 |
| --- | --- | --- | --- | --- | --- |
| 회원가입 | POST | `/auth/signup` | 불필요 | 201, 409, 422 | SignupStep3 |
| 가입 약관 | GET | `/auth/terms` | 불필요 | 200 | SignupStep1~3 |
| 로그인 | POST | `/auth/login` | 불필요 | 200, 401 | Login |
| 로그아웃 | POST | `/auth/logout` | 필요 | 204, 401 | Header |
| 내 정보 | GET | `/auth/me` | 필요 | 200, 401 | Header/My page |
| 가상계좌 생성 | POST | `/accounts` | 필요 | 201, 409 | StartInvesting |
| 내 계좌 | GET | `/accounts/me` | 필요 | 200, 404 | Portfolio |
| 전략 선택 | PUT | `/accounts/{account_id}/strategy` | 필요/소유권 | 200, 404 | StartInvesting |
| 전략 목록 | GET | `/strategies` | 불필요 | 200 | RiskResult/StrategyDetail |
| 현재가 | GET | `/market/stocks/{stock_code}/price` | 필요 | 200, 404, 503 | StockDetail |
| 시장가 주문 | POST | `/orders` | 필요/소유권 | 201, 404, 409, 503 | 주문 UI/Model signal |
| 주문 목록 | GET | `/orders?account_id=` | 필요/소유권 | 200, 404 | 거래내역 |
| 체결 목록 | GET | `/executions?account_id=` | 필요/소유권 | 200, 404 | 거래내역 |
| 포트폴리오 평가 | GET | `/portfolio?account_id=` | 필요/소유권 | 200, 404, 503 | Portfolio/Dashboard |

## 주요 Request/Response

### POST `/auth/signup`

```json
{
  "user_id":"hong01","password":"SafePass!23","name":"홍길동",
  "birthdate":"000101","phone_number":"01012345678","email":"hong@example.com",
  "phone_verified":true,"email_verified":true,
  "agreements":[{"term_code":"B_PRIVACY","version":"1.0","agreed":true}]
}
```

`GET /auth/terms`가 각 약관 코드에서 현재 효력이 있는 최신 버전을 반환한다. Frontend는 Step1의 실제 동의 상태와 이 code/version을 함께 가입 요청으로 전달한다. 모든 필수 동의가 포함되어야 하며, 가입 성공 시 `user_agreements`에 같은 transaction으로 기록된다. 로컬 개발 DB도 운영과 같은 검증을 하려면 migration 후 `data/scripts/seed_signup_terms.py`로 승인된 약관 version을 seed한다.

비밀번호는 8~72자이며 영문·숫자·특수문자 조합 검증은 Frontend와 동일하게 적용한다.

응답 `201`: `{"id":1,"user_id":"hong01","name":"홍길동","email":"hong@example.com","account_status":"ACTIVE"}`

### POST `/auth/login`

요청 `{"user_id":"hong01","password":"SafePass!23"}`

응답 `200`: `{"access_token":"<jwt>","token_type":"bearer"}`

### POST `/accounts`

요청 `{"account_name":"나의 가상 투자계좌"}`

응답 `201`:

```json
{
  "id":"92be9e3e-4364-4428-86c4-b730cc841847","account_name":"나의 가상 투자계좌",
  "initial_cash":"10000000.00","cash_balance":"10000000.00","status":"ACTIVE",
  "selected_strategy_id":null,"created_at":"2026-08-23T12:00:00Z"
}
```

### POST `/orders`

`idempotency_key`는 계좌 안에서 유일하다. 같은 payload로 재전송하면 기존 주문을 반환하고, 다른 payload면 `409 IDEMPOTENCY_CONFLICT`다.

```json
{
  "account_id":"92be9e3e-4364-4428-86c4-b730cc841847","stock_code":"005930",
  "side":"BUY","order_type":"MARKET","quantity":10,"idempotency_key":"client-uuid-0001"
}
```

응답 `201`:

```json
{
  "id":"82b2e790-79ee-4d7f-b94f-f37a7a99a7e6","account_id":"92be9e3e-4364-4428-86c4-b730cc841847",
  "stock_code":"005930","side":"BUY","order_type":"MARKET","quantity":10,
  "status":"FILLED","requested_price":"70000.0000","requested_at":"2026-08-23T12:00:00Z"
}
```

### GET `/portfolio?account_id=...`

```json
{
  "account_id":"92be9e3e-4364-4428-86c4-b730cc841847","cash_balance":"9300000.00",
  "total_purchase_amount":"700000.00","total_evaluation_amount":"710000.00",
  "total_assets":"10010000.00","unrealized_profit":"10000.00","realized_profit":"0.00",
  "return_rate":"1.43",
  "positions":[{"stock_code":"005930","quantity":10,"average_price":"70000.0000","current_price":"71000","purchase_amount":"700000.00","evaluation_amount":"710000.00","unrealized_profit":"10000.00","return_rate":"1.43","realized_profit":"0.00"}]
}
```

## 주요 error code

`AUTHENTICATION_REQUIRED`, `INVALID_TOKEN`, `INVALID_CREDENTIALS`, `ACCOUNT_INACTIVE`, `ACCOUNT_NOT_FOUND`, `ACCOUNT_ALREADY_EXISTS`, `STRATEGY_NOT_FOUND`, `STOCK_NOT_FOUND`, `INSUFFICIENT_CASH`, `INSUFFICIENT_POSITION`, `IDEMPOTENCY_CONFLICT`, `KIS_NOT_CONFIGURED`, `KIS_RATE_LIMIT`, `KIS_UNAVAILABLE`, `DEPENDENCY_UNAVAILABLE`.
