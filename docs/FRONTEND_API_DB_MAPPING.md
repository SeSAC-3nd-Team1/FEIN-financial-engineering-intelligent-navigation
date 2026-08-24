# Frontend → API → DB 매핑

기준: `develop`의 React 화면과 `20260823_0012` migration. 화면의 mock을 단순 복제하지 않고 서비스 상태만 PostgreSQL에 저장한다.

| Frontend 화면 | 현재 데이터/액션 | 필요한 API | DB/외부 데이터 |
| --- | --- | --- | --- |
| Login | Backend 로그인, JWT 영속화·복원, `/auth/me`, 로그아웃 | `POST /api/v1/auth/login`, `POST /auth/logout`, `GET /auth/me` | `users`; bcrypt hash, JWT |
| SignupStep1~3 | 개인정보, 실제 약관 동의 상태·현재 버전, 휴대폰/이메일 OTP mock | `GET /api/v1/auth/terms`, `POST /api/v1/auth/signup` | 기존 `registration_sessions`, `terms`, `registration_agreements`, `users`, `user_agreements`; 실제 OTP provider는 후속 연결 |
| RiskProfile/Result | 설문 입력과 추천 결과 표시 | `POST /api/v1/investor-profile/analyze`, `GET /api/v1/investor-profile/me/latest`, `POST /api/v1/strategy-recommendations`, `GET /api/v1/strategy-recommendations/me/latest` | `investor_profile_assessments`, `strategy_recommendations`, `strategy_recommendation_items` |
| StrategyDetail | `low/value/momentum`, mock backtest | `GET /api/v1/strategies` | `strategies`; 백테스트는 Blob/AI interface 후속 |
| StartInvesting | 전략 배분은 명시적 mock, 시작 시 투자 온보딩·약관 동의·가상계좌 준비·전략 저장 | `/investment/terms`, `/investment/onboardings*` | `investment_onboardings`, `terms`, `user_agreements`, `virtual_accounts`, `cash_ledger`, `strategies`; 신규 계좌 초기금은 선택 투자 금액 |
| Portfolio/Dashboard | 계좌 금액·손익·보유종목은 실제 API, AI 설명·과거 분석은 명시적 mock | `GET /api/v1/accounts/me`, `GET /portfolio?account_id=`, `GET /orders`, `GET /executions` | `virtual_accounts`, `positions`, `orders`, `executions`, `cash_ledger` + Redis/KIS 현재가 |
| StockDetail | 현재가는 실제 API, 차트·재무지표·AI 평가는 명시적 mock | `GET /api/v1/market/stocks/{code}/price` | Redis `price:{code}` → KIS 현재가. 재무지표는 Blob/Data API 후속 |
| InformationExam | 한국 뉴스는 실제 Backend, 금융 상식은 기존 mock | `GET /api/v1/information/news/kr?page=1&size=20` | NAVER API HUB → Redis `information:news:kr:{query}:{page}:{size}`; PostgreSQL/Blob 저장 없음 |
| 자동 운용 주문 처리 | 사용자가 직접 매수·매도하지 않으며, 전략 기반 자동 운용 계층이 MARKET BUY/SELL과 UUID idempotency key를 사용한 뒤 portfolio를 갱신 | `POST/GET /api/v1/orders`, `GET /executions`, `GET /portfolio` | `orders`, `executions`, `positions`, `cash_ledger`; KIS 주문 API 사용 안 함 |

## 확인된 불일치

- Notion의 기존 계좌 문서는 증권 연동 계좌와 KIS 주문/잔고를 전제로 하나, 구현은 서비스 내부 가상계좌다.
- Frontend 인증·계좌·현재가·포트폴리오·주문·체결은 실제 API와 연결되었다. 과거 자산 추이, AI 리밸런싱·설명, 재무지표는 Backend API가 없어 UI에서 `MOCK`으로 구분한다.
- 신규 가상계좌는 사용자가 선택한 투자 금액으로 시작한다. 기존 가상계좌 재사용 시에는 잔액·포지션·원장을 유지하고 추가 입금이나 초기화를 하지 않는다. 사용자 입출금 기능은 이번 MVP 범위 밖이다.

## 실제 호출 흐름

```text
React → FastAPI /market → MarketService → Redis price cache → (miss) KIS 현재가
React → FastAPI /orders → TradingService → MarketService + PostgreSQL transaction
React → FastAPI /portfolio → PostgreSQL positions/account + MarketService
```

React는 KIS URL이나 credential을 알지 못한다. 화면 전환 시 `GET /portfolio` 한 번으로 모든 보유종목의 `current_price`와 평가값을 받고, 종목 상세 또는 사용자가 명시적으로 현재가 확인을 누른 경우에만 개별 Market API를 호출한다. `account_id`는 `/accounts/me` 응답에서 가져오며 소스에 하드코딩하지 않는다.
