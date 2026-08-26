# Frontend → API → DB 매핑

기준: `develop`의 React 화면과 `20260823_0012` migration. 화면의 mock을 단순 복제하지 않고 서비스 상태만 PostgreSQL에 저장한다.

| Frontend 화면 | 현재 데이터/액션 | 필요한 API | DB/외부 데이터 |
| --- | --- | --- | --- |
| Login | Backend 로그인, JWT 영속화·복원, `/auth/me`, 로그아웃 | `POST /api/v1/auth/login`, `POST /auth/logout`, `GET /auth/me` | `users`; bcrypt hash, JWT |
| SignupStep1~3 | 개인정보, 실제 약관 동의 상태·현재 버전, 이메일 OTP 연동 대상 | `GET /api/v1/auth/terms`, `POST /api/v1/auth/email-verifications/send`, `POST /api/v1/auth/email-verifications/verify`, `POST /api/v1/auth/signup` | Redis OTP/가입 증명, `terms`, `users`, `user_agreements`; 휴대폰 인증은 후속 연결 |
| RiskProfile/Result | 설문 입력과 추천 결과 표시 | `POST /api/v1/investor-profile/analyze`, `GET /api/v1/investor-profile/me/latest`, `POST /api/v1/strategy-recommendations`, `GET /api/v1/strategy-recommendations/me/latest` | `investor_profile_assessments`, `strategy_recommendations`, `strategy_recommendation_items` |
| StrategyDetail | 실제 KRX 시세 백테스트와 KOSPI 비교, DB 가용 기간 기반 기간 선택, 데이터 부족 오류 상태 | `GET /api/v1/strategies`, `GET /api/v1/backtest/available-range`, `POST /api/v1/backtest/run` | `strategies.rule_config`, `market_stock_prices`, `market_indices`; 가치 전략은 PIT 재무 가능일 부재로 unavailable |
| StartInvesting | 전략 배분은 명시적 mock, 시작 시 투자 온보딩·약관 동의·가상계좌 준비·전략 저장 | `/investment/terms`, `/investment/onboardings*` | `investment_onboardings`, `terms`, `user_agreements`, `virtual_accounts`, `cash_ledger`, `strategies`; 신규 계좌 초기금은 선택 투자 금액 |
| Portfolio/Dashboard | 홈 통합 조회, 최근 체결·상세 거래내역, 운용방식별 계좌 전환, AI 자동투자와 내 투자 비교, 실제 계좌 평가·당일 기여·자산 이력·5축 feature·AI 리밸런싱 제안·판단 이력 | `GET /api/v1/auth/me`, `GET /accounts/me`, `PUT /accounts/me/active-operation-mode`, `GET /portfolio/home`, `GET /portfolio/comparison`, `GET /portfolio/transactions`, `GET /portfolio`, `GET /portfolio/history`, `GET/POST /portfolio/decisions`, `GET /portfolio/stock-evaluation` | `users.active_operation_mode`, `virtual_accounts`, `positions`, `executions`, `market_stocks`, `portfolio_snapshots`, `strategy_target_weights`, `rebalancing_decisions`, KRX/OpenDART + Redis/KIS 현재가 + AI 리밸런싱·비교 모델 |
| StockDetail | 실제 현재가·차트·종목/재무 요약과 계좌별 5축 feature 평가 | `GET /api/v1/market/stocks/{code}/price`, `GET /market/stocks/{code}/summary`, `GET /market/stocks/{code}/chart`, `GET /portfolio/stock-evaluation` | KRX `market_*`, OpenDART `company_*`, `positions`, `strategy_target_weights`; 1D 분봉/현재가는 KIS |
| InformationExam | 한국 뉴스는 실제 Backend, 금융 상식은 기존 mock | `GET /api/v1/information/news/kr?page=1&size=20` | NAVER API HUB → Redis `information:news:kr:{query}:{page}:{size}`; PostgreSQL/Blob 저장 없음 |
| 자동 운용 주문 처리 | 사용자가 직접 매수·매도하지 않으며, 전략 기반 자동 운용 계층이 MARKET BUY/SELL과 UUID idempotency key를 사용한 뒤 portfolio를 갱신 | `POST/GET /api/v1/orders`, `GET /executions`, `GET /portfolio` | `orders`, `executions`, `positions`, `cash_ledger`; KIS 주문 API 사용 안 함 |

## 확인된 불일치

- Notion의 기존 계좌 문서는 증권 연동 계좌와 KIS 주문/잔고를 전제로 하나, 구현은 서비스 내부 가상계좌다.
- Frontend 인증·계좌·현재가·포트폴리오·주문·체결·자산 이력·5축 feature·리밸런싱 판단 기록은 실제 API와 연결되었다. 계산 불가능한 feature와 결과는 null/unavailable로 표시한다.
- 신규 가상계좌는 사용자가 선택한 투자 금액으로 시작한다. 기존 가상계좌 재사용 시에는 잔액·포지션·원장을 유지하고 추가 입금이나 초기화를 하지 않는다. 사용자 입출금 기능은 이번 MVP 범위 밖이다.

## 실제 호출 흐름

```text
React → FastAPI /market → MarketService → Redis price cache → (miss) KIS 현재가
React → FastAPI /orders → TradingService → MarketService + PostgreSQL transaction
React → FastAPI /portfolio/home → account + portfolio evaluation + snapshot history + validated candidates → AI reason/why-now
React → FastAPI /portfolio/comparison → AUTO/SEMI_AUTO common snapshots + server metrics → AI screen copy
React → FastAPI /portfolio/transactions → PostgreSQL executions + KRX stock metadata
React → FastAPI /portfolio → PostgreSQL positions/account + MarketService
React → FastAPI /accounts/me/active-operation-mode → completed onboarding + mode account → users active selection
React → FastAPI /backtest/available-range → PostgreSQL 주가/KOSPI 공통 가용 기간
React → FastAPI /backtest/run → PostgreSQL KRX stock/index history → 실제 전략/KOSPI 지표
```

React는 KIS URL이나 credential을 알지 못한다. 포트폴리오 홈 화면은 `GET /portfolio/home` 한 번으로
계좌·평가·기간 추이·현금 포함 배분·정렬된 보유종목을 받고, 종목 상세 또는 사용자가 명시적으로
현재가 확인을 누른 경우에만 개별 Market API를 호출한다. 기존 `GET /portfolio`와
`GET /portfolio/history`는 상세 화면과 하위 호환을 위해 유지한다. `account_id`는 운용방식을 지정한
`/accounts/me` 응답에서 가져오며 소스에 하드코딩하지 않는다.

운용방식 전환은 `PUT /accounts/me/active-operation-mode` 응답의 `account.id`로 화면 조회 대상을 바꾸고
`notice`를 전환 직후 팝업으로 표시한다. Backend는 계좌의 운용방식이나 잔액·포지션을 변경하지
않으므로 AUTO/SEMI_AUTO 계좌의 자산과 거래내역은 계속 분리된다. 새로고침 또는 다른 기기에서는
`GET /auth/me`의 `active_operation_mode`를 복원한 뒤 해당 방식의 `/accounts/me`를 조회한다.
