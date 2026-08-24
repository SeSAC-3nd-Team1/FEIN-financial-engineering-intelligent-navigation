# Backend API 명세서

Base URL: `/api/v1` · Content-Type: `application/json` · 인증: `Authorization: Bearer <JWT>`

공통 오류:

```json
{"code":"INSUFFICIENT_CASH","message":"주문 가능한 현금이 부족합니다."}
```

## Endpoint 목록

| 기능 | Method | Endpoint | 인증 | 주요 status | 관련 화면 |
| --- | --- | --- | --- | --- | --- |
| 회원가입 | POST | `/auth/signup` | 불필요 | 201, 400, 409, 422, 503 | SignupStep3 |
| 가입 약관 | GET | `/auth/terms` | 불필요 | 200, 503 | SignupStep1~3 |
| 로그인 | POST | `/auth/login` | 불필요 | 200, 401 | Login |
| 로그아웃 | POST | `/auth/logout` | 필요 | 204, 401 | Header |
| 내 정보 | GET | `/auth/me` | 필요 | 200, 401 | Header/My page |
| 가상계좌 생성 | POST | `/accounts` | 필요 | 201, 409 | StartInvesting |
| 내 계좌 | GET | `/accounts/me` | 필요 | 200, 404 | Portfolio |
| 전략 선택 | PUT | `/accounts/{account_id}/strategy` | 필요/소유권 | 200, 404 | StartInvesting |
| 전략 목록 | GET | `/strategies` | 불필요 | 200 | RiskResult/StrategyDetail |
| 현재가 | GET | `/market/stocks/{stock_code}/price` | 필요 | 200, 404, 503 | StockDetail |
| 당일 1분봉 | GET | `/market/stocks/{stock_code}/candles?interval=1m&limit=120` | 필요 | 200, 404, 422, 503 | StockDetail chart |
| 시장가 주문 | POST | `/orders` | 필요/소유권 | 201, 404, 409, 503 | 전략 기반 자동 운용 계층/Model signal 전용 |
| 주문 목록 | GET | `/orders?account_id=` | 필요/소유권 | 200, 404 | 거래내역 |
| 체결 목록 | GET | `/executions?account_id=` | 필요/소유권 | 200, 404 | 거래내역 |
| 포트폴리오 평가 | GET | `/portfolio?account_id=` | 필요/소유권 | 200, 404, 503 | Portfolio/Dashboard |
| 한국 금융 뉴스 | GET | `/information/news/kr?page=&size=` | 불필요 | 200, 422, 502, 503 | InformationExam |
| 기업 기본정보 | GET | `/companies/{stock_code}` | 불필요 | 200, 404 | Agent/향후 기업 화면 |
| 기업 재무정보 | GET | `/companies/{stock_code}/financials?year=&quarter=` | 불필요 | 200, 404, 422 | Agent/향후 기업 화면 |
| 기업 공시 | GET | `/companies/{stock_code}/disclosures?start_date=&end_date=&disclosure_type=&limit=` | 불필요 | 200, 404, 422 | Disclosure Agent |

## 주요 Request/Response

### POST `/auth/signup`

```json
{
  "user_id":"hong01","password":"SafePass!23","name":"홍길동",
  "birthdate":"000101","phone_number":"01012345678","email":"hong@example.com",
  "phone_verified":true,"email_verified":true,
  "agreements":[
    {"term_code":"A1_THIRD_PARTY","version":"dev-20260823","agreed":true},
    {"term_code":"A2_UNIQUE_ID","version":"dev-20260823","agreed":true},
    {"term_code":"A3_CARRIER","version":"dev-20260823","agreed":true},
    {"term_code":"A4_KCB","version":"dev-20260823","agreed":true},
    {"term_code":"B_PRIVACY","version":"dev-20260823","agreed":true},
    {"term_code":"C_ASSOCIATE_TERMS","version":"dev-20260823","agreed":true}
  ]
}
```

`GET /auth/terms`가 `effective_at <= now()`인 row 중 각 약관 코드의 최신 버전을 반환한다. Frontend는 Step1의 실제 동의 상태와 이 code/version을 함께 가입 요청으로 전달한다. API에는 내부 `term_id` 대신 불변 자연키인 `term_code + version`을 사용하고, Backend가 현재 catalog의 `term_id`로 변환한다.

현재 catalog에 없는 code/version, 아직 효력이 시작되지 않은 version, 최신 버전으로 대체된 과거 version은 `400 INVALID_TERM_VERSION`이다. 필수 약관 누락 또는 `agreed=false`는 `400 REQUIRED_TERMS_NOT_AGREED`다. 사용할 수 있는 필수 catalog 자체가 없으면 조회와 가입 모두 `503 TERMS_CATALOG_UNAVAILABLE`로 fail-closed한다. 가입 성공 시 전달된 동의는 `user_agreements`에 사용자 생성과 같은 transaction으로 기록된다.

비밀번호는 8~72자이며 영문·숫자·특수문자 조합 검증은 Frontend와 동일하게 적용한다.

응답 `201`: `{"id":1,"user_id":"hong01","name":"홍길동","email":"hong@example.com","account_status":"ACTIVE"}`

### GET `/auth/terms`

응답 `200`:

```json
[
  {"term_code":"B_PRIVACY","version":"dev-20260823","title":"개인정보 수집 및 이용 동의","is_required":true},
  {"term_code":"C_ASSOCIATE_TERMS","version":"dev-20260823","title":"준회원 이용약관 동의","is_required":true}
]
```

실제 응답에는 현재 seed된 기존 6종 약관이 포함된다. catalog가 준비되지 않은 경우 빈 배열로 가입을 허용하지 않고 `503`을 반환한다.

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

## 주요 error code

`NAVER_NEWS_NOT_CONFIGURED`, `NAVER_NEWS_UNAVAILABLE`, `NAVER_NEWS_RATE_LIMIT`, `TERMS_CATALOG_UNAVAILABLE`, `REQUIRED_TERMS_NOT_AGREED`, `INVALID_TERM_VERSION`, `VERIFICATION_REQUIRED`, `DUPLICATE_ACCOUNT`, `AUTHENTICATION_REQUIRED`, `INVALID_TOKEN`, `INVALID_CREDENTIALS`, `ACCOUNT_INACTIVE`, `ACCOUNT_NOT_FOUND`, `ACCOUNT_ALREADY_EXISTS`, `STRATEGY_NOT_FOUND`, `STOCK_NOT_FOUND`, `INSUFFICIENT_CASH`, `INSUFFICIENT_POSITION`, `IDEMPOTENCY_CONFLICT`, `KIS_NOT_CONFIGURED`, `KIS_RATE_LIMIT`, `KIS_UNAVAILABLE`, `DEPENDENCY_UNAVAILABLE`.

## KIS 현재가와 가상거래 경계

`GET /market/stocks/{stock_code}/price`와 주문/포트폴리오 평가는 실시간 KIS WebSocket Redis 값, 기존 REST Redis 값, KIS REST 순으로 현재가를 조회한다. `GET /market/stocks/{stock_code}/candles`는 기존 `KisClient`로 KIS 당일 분봉을 조회하고 `market:candles:1m:{stock_code}`에 단기 캐시한다. 상세 계약은 [KIS 실시간 시장가 및 차트 API 명세](KIS_REALTIME_MARKET_API_SPECIFICATION.md)를 따른다. KIS OAuth token은 Redis에 만료 60초 전까지 공유한다. KIS 주문 API는 구현하거나 호출하지 않으며 주문·체결·잔액·원장은 PostgreSQL 가상계좌에서만 변경된다.
