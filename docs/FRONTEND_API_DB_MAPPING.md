# Frontend → API → DB 매핑

기준: `develop`의 React 화면과 `20260823_0012` migration. 화면의 mock을 단순 복제하지 않고 서비스 상태만 PostgreSQL에 저장한다.

| Frontend 화면 | 현재 데이터/액션 | 필요한 API | DB/외부 데이터 |
| --- | --- | --- | --- |
| Login | Backend 로그인, JWT 영속화·복원, `/auth/me`, 로그아웃 | `POST /api/v1/auth/login`, `POST /auth/logout`, `GET /auth/me` | `users`; bcrypt hash, JWT |
| SignupStep1~3 | 개인정보, 약관, 휴대폰/이메일 OTP mock | `POST /api/v1/auth/signup` | 기존 `registration_sessions`, `terms`, `registration_agreements`, `users`, `user_agreements`; 실제 OTP provider는 후속 연결 |
| RiskProfile/Result | 7문항과 전략 추천을 브라우저 state에 저장 | 후속 `investor-profile` API | 기존 Notion 논리 모델 대상. 이번 trading migration에는 포함하지 않음 |
| StrategyDetail | `low/value/momentum`, mock backtest | `GET /api/v1/strategies` | `strategies`; 백테스트는 Blob/AI interface 후속 |
| StartInvesting | 투자금/전략 선택 후 시작 | `POST /api/v1/accounts`, `PUT /accounts/{id}/strategy` | `virtual_accounts`, `cash_ledger`, `strategies` |
| Portfolio/Dashboard | 20종목 mock, 자산/손익/비중 | `GET /api/v1/portfolio?account_id=` | `positions`, `executions`, `cash_ledger` + Redis/KIS 현재가 |
| StockDetail | 종목 mock 현재가/재무지표 | `GET /api/v1/market/stocks/{code}/price` | Redis `price:{code}` → KIS 현재가. 재무지표는 Blob/Data API 후속 |
| 주문 UI(후속) | 현재 화면 없음 | `POST/GET /api/v1/orders`, `GET /executions` | `orders`, `executions`, `positions`, `cash_ledger` |

## 확인된 불일치

- Notion의 기존 계좌 문서는 증권 연동 계좌와 KIS 주문/잔고를 전제로 하나, 구현은 서비스 내부 가상계좌다.
- Frontend 인증은 실제 API와 연결되었다. 포트폴리오·종목·전략 화면 데이터는 아직 dummy를 사용하며 response field 합의 후 치환한다.
- Frontend 투자 시작 금액은 사용자가 선택하지만 계좌 초기금은 Backend 정책 환경변수로 결정한다. 사용자 입출금 기능은 이번 MVP 범위 밖이다.
