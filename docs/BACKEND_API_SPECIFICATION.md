# Backend API 명세서

Base URL: `/api/v1` · Content-Type: `application/json` · 인증: `Authorization: Bearer <JWT>`

공통 오류:

```json
{"code":"INSUFFICIENT_CASH","message":"주문 가능한 현금이 부족합니다."}
```

## Endpoint 목록

| 기능 | Method | Endpoint | 인증 | 주요 status | 관련 화면 |
| --- | --- | --- | --- | --- | --- |
| 이메일 인증번호 발송 | POST | `/auth/email-verifications/send` | 불필요 | 202, 422, 429, 502, 503 | SignupStep3 연동 대상 |
| 이메일 인증번호 확인 | POST | `/auth/email-verifications/verify` | 불필요 | 200, 400, 422, 429, 503 | SignupStep3 연동 대상 |
| 회원가입 | POST | `/auth/signup` | 불필요 | 201, 400, 409, 422, 503 | SignupStep3 |
| 가입 약관 | GET | `/auth/terms` | 불필요 | 200, 503 | SignupStep1~3 |
| 로그인 | POST | `/auth/login` | 불필요 | 200, 401 | Login |
| 로그아웃 | POST | `/auth/logout` | 필요 | 204, 401 | Header |
| 내 정보 | GET | `/auth/me` | 필요 | 200, 401 | Header/My page |
| 투자 약관 | GET | `/investment/terms?strategy_id=` | 필요 | 200, 401, 404, 503 | InvestTerms |
| 투자 시작 생성/갱신 | POST | `/investment/onboardings` | 필요 | 200, 401, 404, 422 | StartInvesting |
| 현재 투자 시작 상태 | GET | `/investment/onboardings/me/current?operation_mode=` | 필요 | 200, 401, 404, 503 | 투자 시작 Flow |
| 운용방식별 투자 시작 상태 | GET | `/investment/onboardings/me` | 필요 | 200, 401, 503 | 로그인 후 Flow 복원 |
| 투자 약관 동의 | POST | `/investment/onboardings/{id}/agreements` | 필요/소유권 | 200, 400, 401, 404, 503 | InvestTerms |
| 가상계좌 준비 | POST | `/investment/onboardings/{id}/account` | 필요/소유권 | 200, 401, 403, 404, 409 | InvestAccount |
| 부족분 가상 입금 | POST | `/investment/onboardings/{id}/deposit` | 필요/소유권 | 200, 401, 404, 409, 422 | InvestDeposit |
| 투자 시작 확정 | POST | `/investment/onboardings/{id}/complete` | 필요/소유권 | 200, 401, 404, 409 | InvestConfirm |
| 가상계좌 생성 | POST | `/accounts` | 필요 | 201, 409 | StartInvesting |
| 내 계좌 | GET | `/accounts/me?operation_mode=` | 필요 | 200, 404 | Portfolio |
| 내 계좌 전체 | GET | `/accounts/me/all` | 필요 | 200 | Portfolio |
| 활성 운용방식 전환 | PUT | `/accounts/me/active-operation-mode` | 필요/소유권 | 200, 409, 422 | Portfolio/Dashboard |
| 전략 선택 | PUT | `/accounts/{account_id}/strategy` | 필요/소유권 | 200, 404 | StartInvesting |
| 전략 목록 | GET | `/strategies` | 불필요 | 200 | RiskResult/StrategyDetail |
| 실제 시세 백테스트 | POST | `/backtest/run` | 불필요 | 200, 404, 422 | StrategyDetail |
| 백테스트 가용 기간 | GET | `/backtest/available-range` | 불필요 | 200, 404 | StrategyDetail |
| 현재가 | GET | `/market/stocks/{stock_code}/price` | 필요 | 200, 404, 503 | StockDetail |
| 당일 1분봉 | GET | `/market/stocks/{stock_code}/candles?interval=1m&limit=120` | 필요 | 200, 404, 422, 503 | StockDetail chart |
| 종목 상세 요약 | GET | `/market/stocks/{stock_code}/summary` | 필요 | 200, 404 | StockDetail |
| 종목 상세 차트 | GET | `/market/stocks/{stock_code}/chart?period=3M` | 필요 | 200, 404, 422, 503 | StockDetail chart |
| 시장가 주문 | POST | `/orders` | 필요/소유권 | 201, 404, 409, 503 | 전략 기반 자동 운용 계층/Model signal 전용 |
| 주문 목록 | GET | `/orders?account_id=` | 필요/소유권 | 200, 404 | 거래내역 |
| 체결 목록 | GET | `/executions?account_id=` | 필요/소유권 | 200, 404 | 거래내역 |
| 포트폴리오 거래내역 | GET | `/portfolio/transactions?account_id=&limit=&cursor=` | 필요/소유권 | 200, 404, 422 | 종목명·거래금액 포함 최신순 cursor pagination |
| 포트폴리오 홈 통합 조회 | GET | `/portfolio/home?account_id=&period=&sort=&order=` | 필요/소유권 | 200, 404, 422, 503 | 계좌·평가·추이·배분·정렬된 보유종목 통합 |
| 포트폴리오 평가 | GET | `/portfolio?account_id=` | 필요/소유권 | 200, 404, 503 | 실제 metadata·당일 기여·목표비중 제안 포함 |
| 포트폴리오 이력 | GET | `/portfolio/history?account_id=&period=` | 필요/소유권 | 200, 404 | 실제 snapshot 수익률과 KOSPI 비교 |
| AI 투자 비교 | GET | `/portfolio/comparison?period=` | 필요 | 200, 401, 409 | AUTO/SEMI_AUTO 외부 현금흐름 조정 TWR과 서버 검증 AI 해설 |
| 종목 5축 feature | GET | `/portfolio/stock-evaluation?account_id=&stock_code=` | 필요/소유권 | 200, 404 | KRX·OpenDART·보유종목 기반 평가 |
| 리밸런싱 판단 기록 | POST | `/portfolio/decisions` | 필요/소유권 | 201, 404, 409 | 현재 서버 제안 수락·보류 기록 |
| 리밸런싱 판단 이력 | GET | `/portfolio/decisions?account_id=` | 필요/소유권 | 200, 404 | 최근 6개월 실제 판단·후속 수익률 |
| 한국 금융 뉴스 | GET | `/information/news/kr?page=&size=` | 불필요 | 200, 422, 502, 503 | InformationExam |
| 기업 기본정보 | GET | `/companies/{stock_code}` | 불필요 | 200, 404 | Agent/향후 기업 화면 |
| 기업 재무정보 | GET | `/companies/{stock_code}/financials?year=&quarter=` | 불필요 | 200, 404, 422 | Agent/향후 기업 화면 |
| 기업 공시 | GET | `/companies/{stock_code}/disclosures?start_date=&end_date=&disclosure_type=&limit=` | 불필요 | 200, 404, 422 | Disclosure Agent |
| 투자성향 AI 분석 | POST | `/investor-profile/analyze` | 필요 | 200, 400, 401, 422, 502, 503, 504 | RiskProfile/RiskResult |
| 최신 투자성향 | GET | `/investor-profile/me/latest` | 필요 | 200, 401, 404 | RiskResult |
| AI 전략 추천 | POST | `/strategy-recommendations` | 필요/소유권 | 201, 401, 403, 404, 502, 503, 504 | RiskResult |
| 최신 AI 전략 추천 | GET | `/strategy-recommendations/me/latest` | 필요 | 200, 401, 404 | RiskResult |

## 주요 Request/Response

### POST `/auth/email-verifications/send`

요청 `{"email":"hong@example.com"}`

응답 `202`:

```json
{"verification_id":"f9c28124-981b-4ee7-8cee-f13b850c2855","expires_in_seconds":300,"resend_after_seconds":60}
```

ACS Email로 6자리 인증번호를 보내며 원문 인증번호는 Redis에 저장하지 않는다. 같은 이메일은 기본
60초 뒤 재발송할 수 있고 시간당 5회, 요청 IP는 시간당 20회로 제한한다. IP 식별은 ASGI server가
검증한 `request.client.host`를 사용하며 클라이언트가 직접 보낸 전달 헤더는 애플리케이션에서 신뢰하지 않는다.

### POST `/auth/email-verifications/verify`

```json
{"verification_id":"f9c28124-981b-4ee7-8cee-f13b850c2855","code":"123456"}
```

응답 `200`: `{"verification_token":"<single-use-token>","expires_in_seconds":1800}`

인증번호는 기본 5회까지만 시도할 수 있다. 반환된 증명은 해당 이메일의 회원가입에만 사용할 수 있고,
Redis에서 예약 후 DB commit 시 소비되므로 재사용할 수 없다.

### POST `/auth/signup`

```json
{
  "user_id":"hong01","password":"SafePass!23","name":"홍길동",
  "birthdate":"000101","phone_number":"01012345678","email":"hong@example.com",
  "email_verification_token":"<single-use-token>",
  "agreements":[
    {"term_code":"B_PRIVACY","version":"dev-20260823","agreed":true},
    {"term_code":"C_ASSOCIATE_TERMS","version":"dev-20260823","agreed":true},
    {"term_code":"AI_PERSONALIZATION","version":"dev-20260823","agreed":false}
  ]
}
```

클라이언트가 인증 여부 boolean을 선언할 수 없다. Backend는 `email_verification_token`의 대상 이메일,
TTL, single-use 상태를 Redis에서 확인한다. 휴대폰 번호는 일반 가입 정보로만 저장하며 휴대폰 인증
API나 클라이언트 선언 인증 상태는 지원하지 않는다.

이 계약은 기존 `phone_verified`/`email_verified` payload와 호환되지 않는다. Backend에서 이를 허용하면
이메일 소유 검증을 우회할 수 있으므로 호환 모드를 제공하지 않는다. 따라서 이 API를 호출하는 배포
단위가 `email-verifications/send` → `verify`에서 받은 token을 전달할 준비가 된 뒤에만 배포한다.

`GET /auth/terms`가 `effective_at <= now()`인 row 중 각 약관 코드의 최신 버전을 반환한다. Frontend는 Step1의 실제 동의 상태와 이 code/version을 함께 가입 요청으로 전달한다. API에는 내부 `term_id` 대신 불변 자연키인 `term_code + version`을 사용하고, Backend가 현재 catalog의 `term_id`로 변환한다.

현재 catalog에 없는 code/version, 아직 효력이 시작되지 않은 version, 최신 버전으로 대체된 과거 version은 `400 INVALID_TERM_VERSION`이다. 필수 약관 누락 또는 `agreed=false`는 `400 REQUIRED_TERMS_NOT_AGREED`다. 사용할 수 있는 필수 catalog 자체가 없으면 조회와 가입 모두 `503 TERMS_CATALOG_UNAVAILABLE`로 fail-closed한다. 가입 성공 시 전달된 동의는 `user_agreements`에 사용자 생성과 같은 transaction으로 기록된다.

비밀번호는 8~72자이며 영문·숫자·특수문자 조합 검증은 Frontend와 동일하게 적용한다.

응답 `201`: `{"id":1,"user_id":"hong01","name":"홍길동","email":"hong@example.com","account_status":"ACTIVE","active_operation_mode":null,"operation_mode_changed_at":null}`

`GET /auth/me`도 같은 사용자 필드로 현재 활성 운용방식을 반환한다. 투자 시작을 아직 완료하지 않은
사용자는 `active_operation_mode=null`일 수 있으며, Frontend는 임의 계좌를 선택하지 않고 투자 시작
상태를 확인한다.

### GET `/auth/terms`

응답 `200`:

```json
[
  {"term_code":"B_PRIVACY","version":"dev-20260823","title":"개인정보 수집 및 이용 동의","is_required":true},
  {"term_code":"C_ASSOCIATE_TERMS","version":"dev-20260823","title":"준회원 이용약관 동의","is_required":true}
]
```

현재 가입 catalog는 `B_PRIVACY`, `C_ASSOCIATE_TERMS`, `AI_PERSONALIZATION`만 포함한다. 휴대폰·본인확인 사업자용 약관은 휴대폰 인증을 도입할 때 함께 연결한다. catalog가 준비되지 않은 경우 빈 배열로 가입을 허용하지 않고 `503`을 반환한다.

### POST `/auth/login`

요청 `{"user_id":"hong01","password":"SafePass!23"}`

응답 `200`: `{"access_token":"<jwt>","token_type":"bearer"}`

### POST `/accounts`

요청 `{"account_name":"나의 가상 투자계좌","operation_mode":"SEMI_AUTO"}`

응답 `201`:

```json
{
  "id":"92be9e3e-4364-4428-86c4-b730cc841847","account_name":"나의 가상 투자계좌",
  "operation_mode":"SEMI_AUTO","initial_cash":"0.00","cash_balance":"0.00","status":"ACTIVE",
  "selected_strategy_id":null,"created_at":"2026-08-23T12:00:00Z"
}
```

투자 시작 화면의 신규/기존 계좌 분기는 `/investment/onboardings/{id}/account`를 사용한다. 이 API는
외부 증권사 계좌를 연동하지 않으며, 같은 운용방식의 가상계좌가 없으면 0원 계좌를 생성하고 있으면
재사용한다. 투자 예정 금액의 부족분은 별도 `/deposit` API로 정확히 한 번 입금한다.
상세 계약은 [가상투자 시작 Backend API 명세](INVESTMENT_ONBOARDING_API_SPECIFICATION.md)를 따른다.

### PUT `/accounts/me/active-operation-mode`

```json
{"operation_mode":"AUTO"}
```

같은 계좌의 `operation_mode`를 수정하거나 자산·포지션·거래내역을 옮기지 않는다. 사용자가 해당
운용방식의 투자 시작을 완료했고 `ACTIVE` 상태인 별도 계좌가 있을 때만 현재 활성 계좌 선택을
변경한다. 대상 계좌나 완료된 온보딩이 없으면 `409 OPERATION_MODE_ACCOUNT_NOT_READY`, 계좌가
비활성이면 `409 OPERATION_MODE_ACCOUNT_NOT_ACTIVE`다. 같은 방식을 재전송하면 변경 시각을 갱신하지
않고 `changed=false`를 반환한다.

응답의 `notice`는 별도 알림 저장 없이 전환 직후 팝업에 사용할 일회성 안내 계약이다.

```json
{
  "previous_operation_mode":"SEMI_AUTO",
  "operation_mode":"AUTO",
  "changed":true,
  "changed_at":"2026-08-25T15:30:00Z",
  "account":{
    "id":"92be9e3e-4364-4428-86c4-b730cc841847",
    "account_name":"자동 운용 계좌",
    "operation_mode":"AUTO",
    "initial_cash":"1000000.00",
    "cash_balance":"750000.00",
    "status":"ACTIVE",
    "selected_strategy_id":"low",
    "created_at":"2026-08-25T12:00:00Z"
  },
  "notice":{
    "code":"OPERATION_MODE_CHANGED",
    "title":"운용방식이 변경됐어요",
    "message":"확인하고 실행 계좌에서 자동으로 운용 계좌로 전환했어요. 각 계좌의 자산과 거래내역은 이동하지 않고 그대로 유지됩니다."
  }
}
```

### POST `/orders`

`idempotency_key`는 계좌 안에서 유일하다. 같은 payload로 재전송하면 기존 주문을 반환하고, 다른 payload면 `409 IDEMPOTENCY_CONFLICT`다. 가격×수량을 원화 소수 둘째 자리로 반올림한 주문금액이 1원 미만이면 포지션이나 원장을 만들지 않고 `409 ORDER_AMOUNT_TOO_SMALL`을 반환한다.

```json
{
  "account_id":"92be9e3e-4364-4428-86c4-b730cc841847","stock_code":"005930",
  "side":"BUY","order_type":"MARKET","quantity":10.125,"idempotency_key":"client-uuid-0001"
}
```

응답 `201`:

```json
{
  "id":"82b2e790-79ee-4d7f-b94f-f37a7a99a7e6","account_id":"92be9e3e-4364-4428-86c4-b730cc841847",
  "stock_code":"005930","side":"BUY","order_type":"MARKET","quantity":"10.12500000",
  "status":"FILLED","requested_price":"70000.0000","requested_at":"2026-08-23T12:00:00Z"
}
```

### GET `/portfolio/home?account_id=...&period=3M&sort=weight&order=desc`

포트폴리오 홈 첫 화면에 필요한 실제 계좌, 평가 요약, 기간별 자산 이력, 현금을 포함한 자산
배분, 보유종목, 당일 기여와 리밸런싱 제안을 한 번에 반환한다. `period`는 `1M`, `3M`, `1Y`,
`ALL`이며 기본값은 `3M`이다. `sort`는 `stock_name`, `weight`, `purchase_amount`,
`return_rate`, `order`는 `asc`, `desc`를 허용한다. 기본 정렬은 `weight desc`다.

`allocations`는 각 보유종목의 현재 평가금액과 현금 항목을 함께 반환한다. `valuation_as_of`는
보유종목 가격 기준시각 중 가장 최신 시각이며, 보유종목이 없으면 `null`이다. `price_sources`는
평가에 실제 사용된 `KIS`, `KRX` 등의 source 목록이다. 이 GET은 기존 포트폴리오 평가와
snapshot 이력을 조합하는 읽기 전용 API이며 거래나 snapshot을 생성하지 않는다.

```json
{
  "account": {
    "id": "92be9e3e-4364-4428-86c4-b730cc841847",
    "account_name": "나의 가상 투자계좌",
    "operation_mode": "SEMI_AUTO",
    "status": "ACTIVE",
    "selected_strategy_id": "low"
  },
  "summary": {
    "cash_balance": "300000.00",
    "total_purchase_amount": "700000.00",
    "total_evaluation_amount": "710000.00",
    "total_assets": "1010000.00",
    "unrealized_profit": "10000.00",
    "realized_profit": "0.00",
    "return_rate": "1.43",
    "today_profit": "5000.00",
    "top_contributor": null
  },
  "trend": {
    "account_id": "92be9e3e-4364-4428-86c4-b730cc841847",
    "period": "3M",
    "benchmark_name": "KOSPI",
    "items": []
  },
  "allocations": [
    {"type":"STOCK","stock_code":"005930","name":"삼성전자","amount":"710000.00","weight":"70.30"},
    {"type":"CASH","stock_code":null,"name":"현금","amount":"300000.00","weight":"29.70"}
  ],
  "positions": [],
  "contributions": [],
  "strategy_targets_available": false,
  "rebalancing_insight": {
    "status": "UNAVAILABLE",
    "summary": "적용 가능한 전략 목표 비중이 없습니다.",
    "model_version": null,
    "generated_at": null
  },
  "rebalancing_proposals": [],
  "valuation_as_of": "2026-08-25T10:30:00+09:00",
  "price_sources": ["KIS"]
}
```

`rebalancing_proposals`는 Backend가 목표 비중으로 검증한 조정 후보 중 AI 모델이 선택한 항목만
반환한다. 각 항목에는 기존 비중·금액 필드와 함께 `priority`, `reason`, `why_now`,
`source="AI"`가 포함된다. 모델이 후보에 없는 종목이나 변경된 금액을 반환하면 그 결과는
프론트에 전달하지 않는다. 모델 미설정·timeout·provider 오류·schema 오류는 홈 전체를 실패시키지
않고 `rebalancing_insight.status="UNAVAILABLE"`, 빈 제안 목록으로 격리한다. 상세 계약은
[AI 리밸런싱 제안 계약](AI_REBALANCING_API_SPECIFICATION.md)을 따른다.

### GET `/portfolio/transactions?account_id=...&limit=20&cursor=...`

실제 체결된 거래를 `executed_at DESC, id DESC` 순서로 반환한다. `limit` 기본값은 20이고
1~100을 허용한다. 홈의 최근 거래 2~3건은 같은 API에 `limit=3`을 사용한다. 다음 페이지가
있으면 마지막 반환 항목의 체결시각과 실행 ID를 담은 opaque `next_cursor`를 반환하며, 클라이언트는
값을 해석하거나 변경하지 않고 다음 요청의 `cursor`로 전달한다.

종목명은 KRX `market_stocks`를 LEFT JOIN하므로 metadata가 없으면 `null`이다. 거래금액은 실제
체결 수량과 체결가의 곱을 원 단위 소수점 둘째 자리로 반올림한 값이다. 소유하지 않은 계좌는
`404 ACCOUNT_NOT_FOUND`, 손상되거나 지원하지 않는 cursor는
`422 INVALID_TRANSACTION_CURSOR`를 반환한다.

```json
{
  "account_id": "92be9e3e-4364-4428-86c4-b730cc841847",
  "items": [
    {
      "id": 42,
      "order_id": "82b2e790-79ee-4d7f-b94f-f37a7a99a7e6",
      "stock_code": "005930",
      "stock_name": "삼성전자",
      "side": "BUY",
      "quantity": "1.25000000",
      "execution_price": "70000.0000",
      "transaction_amount": "87500.00",
      "executed_at": "2026-08-25T10:30:00+09:00"
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

### GET `/portfolio?account_id=...`

```json
{
  "account_id":"92be9e3e-4364-4428-86c4-b730cc841847","cash_balance":"9300000.00",
  "total_purchase_amount":"700000.00","total_evaluation_amount":"710000.00",
  "total_assets":"10010000.00","unrealized_profit":"10000.00","realized_profit":"0.00",
  "return_rate":"1.43","today_profit":"10000.00",
  "top_contributor":{"stock_code":"005930","stock_name":"삼성전자","amount":"10000.00","share_rate":"100.00"},
  "strategy_targets_available":false,"rebalancing_proposals":[],
  "positions":[{"stock_code":"005930","stock_name":"삼성전자","sector":"반도체","quantity":"10.12500000","average_price":"70000.0000","current_price":"71000","previous_close":"70000","change_rate":"1.43","purchase_amount":"708750.00","evaluation_amount":"718875.00","unrealized_profit":"10125.00","return_rate":"1.43","realized_profit":"0.00","weight":"7.09","today_profit":"10125.00","price_source":"KIS","price_as_of":"2026-08-25T09:00:00+09:00"}]
}
```

종목 metadata는 KRX, 현재가·전일종가는 Redis/KIS를 사용한다. 목표 비중은
`strategy_target_weights`에 실제 유효 데이터가 있을 때만 계산하며 임의 균등 비중을 만들지
않는다. 이 GET은 읽기 전용이며 `portfolio_snapshots`를 변경하지 않는다. 스냅샷은
`Portfolio Daily Snapshot` GitHub Actions가 평일 장 마감 후 19:00 KST에 활성 계좌를 평가해
18:30 KST KRX 동기화로 적재된 당일·전일 종가를 기준으로 계좌·일자별 UPSERT한다. 휴장일은
KOSPI 당일 종가가 없어 저장을 건너뛴다. 필요하면 `workflow_dispatch`로 같은 작업을 수동
실행할 수 있다.

### GET `/portfolio/history?account_id=...&period=1Y`

`period`는 `1M`, `3M`, `1Y`, `ALL`을 지원한다. 실제 snapshot의 첫 값을 0% 기준으로 하고,
첫 snapshot 날짜의 직전 KRX KOSPI 종가를 benchmark의 0% 기준으로 정규화한다. 동일 날짜의
provider 표기 중복은 한 건으로 축약한다. 데이터가 부족하면 합성 이력을
만들지 않고 실제로 저장된 항목만 반환한다.

### GET `/portfolio/stock-evaluation?account_id=...&stock_code=005930`

`stock-feature-v1`의 안정성·재무 건전성·성장성·방어력·분산 기여를 0~100으로 반환한다.
각 축은 `score`, `AVAILABLE/UNAVAILABLE`, 실제 산출 근거를 포함한다. KRX 가격 표본,
OpenDART FY 재무 또는 다른 보유종목 표본이 부족하면 해당 축만 null이다. 상세 산식은
`docs/PORTFOLIO_ANALYTICS_SPECIFICATION.md`를 따른다.

### POST `/portfolio/decisions`

```json
{"account_id":"92be9e3e-4364-4428-86c4-b730cc841847","stock_code":"005930","decision":"ACCEPTED","idempotency_key":"<uuid>"}
```

비중·금액·BUY/SELL은 요청에서 받지 않고 Backend가 현재 포트폴리오 제안에서 다시 산출한다.
유효한 제안이 없으면 `409 REBALANCING_PROPOSAL_NOT_FOUND`다. 같은 계좌의 idempotency key를
재전송하면 기존 기록을 반환한다.
판단 기준 자산은 과거 장마감 snapshot이 아니라 이 요청에서 다시 평가한 현재 포트폴리오
`total_assets`이며, 가격 기준일도 함께 저장한다.

### GET `/portfolio/decisions?account_id=...`

최근 6개월의 수락·보류 개수와 판단 당시 서버 제안값을 반환한다. 판단 기준일보다 뒤의 일별
스냅샷이 있으면 실제 포트폴리오 수익률을 제공한다. 반사실 수익률은 제공하지 않는다.
판단별 경과 기간이 다르므로 수락·보류 성과 평균은 제공하지 않는다.

### GET `/information/news/kr`

Provider는 NAVER Cloud Platform NAVER API HUB Search News API의 `GET /search/v1/news`다. `page` 기본값은 1이고 최솟값은 1이다. `size` 기본값은 20이며 1~50만 허용한다. Backend는 `query=NEWS_SEARCH_QUERY`, `display=size`, `start=((page-1)*size)+1`, `sort=date`로 호출한다. 계산된 `start`가 NAVER 허용 범위인 1~1000을 벗어나면 provider를 호출하지 않고 `422`를 반환한다.

응답 `200`:

```json
{
  "items": [
    {
      "id": "8d58f6e8b17f38f43001f17a",
      "title": "삼성전자 주가 상승",
      "summary": "외국인 순매수가 증가했습니다.",
      "thumbnail": null,
      "publisher": "hankyung.com",
      "publishedAt": "2026-08-23T15:42:00+09:00",
      "link": "https://www.hankyung.com/article/123"
    }
  ],
  "totalCount": 1234,
  "updatedAt": "2026-08-23T15:50:00+09:00"
}
```

- `originallink`를 우선하고 없으면 NAVER `link`를 사용한다.
- `id`는 최종 link의 SHA-256 앞 24자리이므로 같은 기사는 같은 ID를 가진다.
- title/description의 HTML tag와 entity는 Backend에서 제거·해제한다.
- NAVER 응답에 언론사 필드가 없으므로 publisher는 최종 link hostname이며 매체명을 추측하지 않는다.
- Redis key는 `information:news:kr:{query}:{page}:{size}`, 기본 TTL은 300초다.
- Redis read/write 장애는 provider 호출 또는 정상 응답을 막지 않는다.
- 뉴스는 PostgreSQL과 Azure Blob에 저장하지 않고 뉴스 본문도 scraping하지 않는다.

오류는 설정 누락 `503 NAVER_NEWS_NOT_CONFIGURED`, timeout/4xx/5xx/응답 schema 오류 `502 NAVER_NEWS_UNAVAILABLE`, provider 429 `503 NAVER_NEWS_RATE_LIMIT`이다. API key header와 실제 credential은 응답·exception·로그에 포함하지 않는다.

## OpenDART 기업 조회

데이터 출처는 금융감독원 OpenDART이며 API key는 data 수집 container에서만 사용한다. 공개
FastAPI endpoint는 PostgreSQL에 적재된 정제 결과만 읽고 외부 사용자의 호출로 전체 수집
job을 실행하지 않는다. `{stock_code}`는 선행 0을 포함한 문자열이다.

### GET `/companies/{stock_code}`

기업 기본정보를 반환한다. 응답 `200`:

```json
{"corp_code":"00126380","stock_code":"005930","corp_name":"삼성전자","corp_name_eng":"Samsung Electronics Co., Ltd.","stock_name":"삼성전자","market":"Y","ceo_name":"대표이사","jurir_no":"...","bizr_no":"...","address":"...","homepage_url":"https://...","ir_url":"https://...","phone_number":"...","industry_code":"264","established_date":"1969-01-13","accounting_month":"12","source":"OpenDART"}
```

### GET `/companies/{stock_code}/financials`

Query parameter는 `year`(선택, `YYYY`)와 `quarter`(선택, `Q1|Q2|Q3|FY`)다. 계정 ID를
우선해 집계한 매출액, 영업이익, 순이익, 자산·부채·자본, 영업·투자·재무 현금흐름을
보고서별로 반환한다. 금액이 공시에 없으면 `null`이다.

```json
{"stock_code":"005930","items":[{"business_year":"2025","report_code":"11011","quarter":"FY","fs_div":"CFS","revenue":"300000000000000.00","operating_income":null,"net_income":null,"total_assets":null,"total_liabilities":null,"total_equity":null,"operating_cash_flow":null,"investing_cash_flow":null,"financing_cash_flow":null}],"source":"OpenDART"}
```

### GET `/companies/{stock_code}/disclosures`

Query parameter는 `start_date`, `end_date`(선택, `YYYY-MM-DD`), `disclosure_type`(선택,
보고서명 부분 일치), `limit`(기본 20, 1~100)이다. 최신 접수일과 접수번호 순으로 반환한다.

```json
{"stock_code":"005930","items":[{"receipt_no":"202608240001","corp_code":"00126380","stock_code":"005930","corp_name":"삼성전자","report_name":"사업보고서","filer_name":"삼성전자","receipt_date":"2026-08-24","remarks":null}],"source":"OpenDART"}
```

세 endpoint 모두 종목이 없으면 `404`를 반환한다.

```json
{"code":"COMPANY_NOT_FOUND","message":"OpenDART 기업정보를 찾을 수 없습니다."}
```

잘못된 날짜, `year`, `quarter`, `limit`은 FastAPI validation의 `422` 응답이다.

### POST `/investor-profile/analyze`

인증된 사용자가 `v1` 설문의 8개 `question_id`와 `option_id`를 제출하면 Backend가 서버 카탈로그로 검증·정규화하고 Azure OpenAI 분석 결과를 PostgreSQL에 저장한 뒤 `assessment_id`와 함께 반환한다. 원본 답변은 저장하지 않는다.

상세 request/response, 전체 문항 ID, 선택지 ID와 오류 계약은 [투자성향 AI 분석 API 명세](INVESTOR_PROFILE_API_SPECIFICATION.md)를 따른다.

### POST `/strategy-recommendations`

인증 사용자가 소유한 `assessment_id`를 전달하면 Backend가 저장된 성향과 활성 전략 catalog를 최근 8년 데이터로 학습된 추천 모델에 전달한다. 구조화 출력과 전략·순위·점수를 검증한 뒤 버전 정보와 함께 저장한다. 상세 계약은 [AI 전략 추천 API 명세](STRATEGY_RECOMMENDATION_API_SPECIFICATION.md)를 따른다.

## 주요 error code

`COMPANY_NOT_FOUND`, `CHART_DATA_UNAVAILABLE`, `AI_PERSONALIZATION_CONSENT_REQUIRED`, `AI_NOT_CONFIGURED`, `AI_ANALYSIS_UNAVAILABLE`, `AI_ANALYSIS_TIMEOUT`, `AI_INVALID_RESPONSE`, `AI_RECOMMENDATION_NOT_CONFIGURED`, `AI_RECOMMENDATION_UNAVAILABLE`, `AI_RECOMMENDATION_TIMEOUT`, `AI_INVALID_RECOMMENDATION`, `INVESTOR_PROFILE_NOT_FOUND`, `STRATEGY_RECOMMENDATION_NOT_FOUND`, `STRATEGY_CATALOG_UNAVAILABLE`, `INVALID_QUESTIONNAIRE_VERSION`, `INVALID_INVESTOR_ANSWERS`, `NAVER_NEWS_NOT_CONFIGURED`, `NAVER_NEWS_UNAVAILABLE`, `NAVER_NEWS_RATE_LIMIT`, `TERMS_CATALOG_UNAVAILABLE`, `REQUIRED_TERMS_NOT_AGREED`, `INVALID_TERM_VERSION`, `VERIFICATION_REQUIRED`, `DUPLICATE_ACCOUNT`, `AUTHENTICATION_REQUIRED`, `INVALID_TOKEN`, `INVALID_CREDENTIALS`, `ACCOUNT_INACTIVE`, `ACCOUNT_NOT_FOUND`, `ACCOUNT_ALREADY_EXISTS`, `STRATEGY_NOT_FOUND`, `STOCK_NOT_FOUND`, `ORDER_AMOUNT_TOO_SMALL`, `INSUFFICIENT_CASH`, `INSUFFICIENT_POSITION`, `IDEMPOTENCY_CONFLICT`, `INVALID_TRANSACTION_CURSOR`, `KIS_NOT_CONFIGURED`, `KIS_RATE_LIMIT`, `KIS_UNAVAILABLE`, `DEPENDENCY_UNAVAILABLE`.

## KIS 현재가와 가상거래 경계

`GET /market/stocks/{stock_code}/price`와 주문/포트폴리오 평가는 실시간 KIS WebSocket Redis 값, 기존 REST Redis 값, KIS REST 순으로 현재가를 조회한다. `GET /market/stocks/{stock_code}/candles`는 기존 `KisClient`로 KIS 당일 분봉을 조회하고 `market:candles:1m:{stock_code}`에 단기 캐시한다. 상세 계약은 [KIS 실시간 시장가 및 차트 API 명세](KIS_REALTIME_MARKET_API_SPECIFICATION.md)를 따른다. KIS OAuth token은 Redis에 만료 60초 전까지 공유한다. KIS 주문 API는 구현하거나 호출하지 않으며 주문·체결·잔액·원장은 PostgreSQL 가상계좌에서만 변경된다.

## StockDetail 실제 데이터 계약

`GET /market/stocks/{stock_code}/price`는 PostgreSQL을 조회하지 않고 Redis/KIS에서 현재가·전일 대비·등락률·거래량을 반환하는 유일한 현재가 계약이다. `GET /market/stocks/{stock_code}/summary`는 KIS를 호출하지 않고 KRX 종목 마스터·최근 일별시세와 OpenDART 최근 연결 사업보고서를 조합한다. 호환성을 위해 summary의 `price`, `previous_close`, `change_amount`, `change_rate`, `volume` 필드는 유지하지만 항상 `null`이며 Frontend는 `/price` 응답만 사용한다. 외부 데이터가 없거나 계산할 수 없는 필드는 `0`이나 추정값 대신 `null`을 반환한다. PER은 `시가총액/순이익`, PBR은 `시가총액/자본`, ROE는 `순이익/자본*100`이며 분모가 0 이하이면 `null`이다. 배당 원천을 아직 연결하지 않았으므로 `dividend_yield`는 `null`이다. 재무비율은 최신 연간 공시 단순 비율로 금융업 등 업종별 조정이나 TTM 계산을 하지 않는다.

```json
{
  "stock_code":"005930","stock_name":"삼성전자","market":"KOSPI","sector":"전기전자",
  "listing_date":"1975-06-11","listed_shares":5969782550,"security_type":"주권",
  "description":"삼성전자은(는) KOSPI 상장 기업입니다.",
  "price":null,"previous_close":null,"change_amount":null,"change_rate":null,"volume":null,
  "market_cap":"423000000000000","per":"14.1","pbr":"1.4","roe":"9.9","dividend_yield":null,
  "financial_year":"2025","as_of":"2026-08-24T06:30:00Z",
  "sources":{"price":null,"market":"KRX","financial":"OpenDART"}
}
```

`GET /market/stocks/{stock_code}/chart`의 `period`는 `1D|1W|3M|6M|1Y|5Y`다. `1D`는 KRX DB 존재 여부와 무관하게 KIS 당일 1분봉 최대 390개로 정규장 전체를 조회한다. 그 외 기간은 종목별 최신 KRX 거래일을 기간의 끝으로 삼아 PostgreSQL의 일별 OHLCV를 날짜 오름차순으로 반환한다. 저장된 기간에 실제 행이 없으면 `404 CHART_DATA_UNAVAILABLE`이며 빈 선이나 합성 시계열을 만들지 않는다.

```json
{"stock_code":"005930","period":"3M","source":"KRX","as_of":"2026-08-24T00:00:00Z","items":[{"date":"2026-08-24","open":"70000","high":"71500","low":"69800","close":"71000","volume":1234567}]}
```

## 실제 시세 Strategy Backtest

`POST /backtest/run`은 `market_stock_prices`와 `market_indices`의 실제 KRX 일별 종가만 사용한다. 합성 가격, 임의 drift, Mock 지표 fallback은 사용하지 않는다.

`GET /backtest/available-range`는 주가 lookback 260일을 확보한 최초일과 주가·KOSPI의 공통 최종일을 반환한다. Frontend는 이 값을 추천 기간과 직접 입력의 경계로 사용하며 공개 DB에 없는 연도를 하드코딩하지 않는다.

```json
{"minDate":"2022-09-18","maxDate":"2026-08-24"}
```

```json
{
  "strategyId":"low",
  "periodId":"custom",
  "periodLabel":"직접 설정",
  "periodDescription":"",
  "startDate":"2022-01-01",
  "endDate":"2026-08-01"
}
```

응답 `200`:

```json
{
  "strategyId":"low","strategyName":"저변동성 전략",
  "period":{"id":"custom","label":"직접 설정","startDate":"2022-01-01","endDate":"2026-08-01","description":""},
  "series":[{"t":"2022-01-03","strategy":0.0,"benchmark":0.0}],
  "metrics":{"cumulativeReturn":12.3,"cagr":2.7,"mdd":-14.2,"volatility":11.8,"sharpe":0.29},
  "benchmarkName":"KOSPI","benchmarkMetrics":{"cumulativeReturn":8.1,"mdd":-22.4}
}
```

- 시작일 직전 최신 시가총액 상위 100종목으로 universe를 고정한다. 이는 미래 universe 참조를 막지만 원천 master의 보유 범위에 따른 생존편향 가능성은 남는다.
- `low_volatility`은 직전 60거래일 수익률을 모두 보유한 종목 중 변동성이 낮은 10종목, `momentum`은 직전 126거래일을 모두 보유한 종목 중 누적수익률이 높은 10종목을 선택한다.
- 초기 구성과 월별 리밸런싱의 신규 편입 후보는 해당 선택일 종가가 있어 실제 거래 가능한 종목으로 제한한다.
- 동일가중 포트폴리오는 월이 바뀐 첫 거래일 종가까지 기존 종목 수익을 반영한 뒤 재선정하며, 새 구성은 다음 거래일부터 적용한다.
- 거래정지 등으로 종가가 없는 날에는 직전 관측 가격으로 평가하고, 거래 재개일에는 마지막 관측 종가부터 재개 종가까지의 변동을 한 번에 반영한다.
- 원천 `close_price`는 수정주가가 아니다. 상장주식수 변동으로 탐지한 액면분할·병합 등 corporate action 당일은 수익률 계산에서 제외하고 해당 종가를 새 기준가로 연결한다. corporate action이 팩터 lookback 안에 있으면 해당 종목은 그 리밸런싱 후보에서 제외한다. 배당을 포함한 총수익률은 제공하지 않는다.
- CAGR은 실제 경과일, 변동성은 일수익률 표준편차에 `sqrt(252)`, Sharpe는 무위험수익률 0 가정으로 계산한다. MDD는 누적자산 고점 대비 최대 하락률이다.
- 가치 전략은 현재 `company_financials`에 실제 공시 가능일이 없어 PIT 안전한 계산을 할 수 없으므로 `422 BACKTEST_STRATEGY_UNAVAILABLE`을 반환한다.
- universe, 전략 lookback 또는 KOSPI 데이터가 부족하면 `404 BACKTEST_DATA_UNAVAILABLE`이며 합성 결과를 만들지 않는다.
