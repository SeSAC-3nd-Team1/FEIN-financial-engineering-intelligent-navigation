# 가상투자 데이터 명세서

Source of truth: `data/db/migrations/versions/20260823_0012_virtual_trading.py`부터 `20260825_0019_fractional_quantities.py`까지. PostgreSQL 17/Azure Database for PostgreSQL 호환.

| Table.Column | PostgreSQL Type | PK/FK/NULL/Default | Constraint/Index | 설명 |
| --- | --- | --- | --- | --- |
| strategies.id | varchar(30) | PK, NOT NULL |  | Frontend strategyId (`low/value/momentum`) |
| strategies.name/description | varchar(100)/text | NOT NULL |  | 표시명/설명 |
| strategies.risk_level | varchar(20) | NOT NULL | LOW/MEDIUM/HIGH | 위험도 |
| strategies.rebalance_cycle | varchar(30) | NOT NULL |  | 리밸런싱 주기 |
| strategies.rule_config | jsonb | NOT NULL |  | 모델과의 versionable interface |
| virtual_accounts.id | uuid | PK |  | 가상계좌 ID |
| virtual_accounts.user_id | bigint | FK users.id, NOT NULL | UNIQUE, RESTRICT | 사용자당 MVP 단일 계좌 |
| virtual_accounts.initial_cash/cash_balance | numeric(20,2) | NOT NULL | >0 / >=0 | 정책 초기금/현재 cash snapshot |
| virtual_accounts.status | varchar(20) | DEFAULT ACTIVE | CHECK, index | ACTIVE/SUSPENDED/CLOSED |
| virtual_accounts.selected_strategy_id | varchar(30) | FK strategies.id, NULL | SET NULL | 선택 전략 |
| positions.id | bigint identity | PK |  | 포지션 ID |
| positions.account_id/stock_code | uuid/varchar(12) | FK, NOT NULL | UNIQUE pair, account index | 계좌별 종목 |
| positions.quantity | numeric(20,8) | NOT NULL | >=0 | 소수점 매매를 포함한 현재 보유수량 |
| positions.average_price | numeric(20,4) | NOT NULL | >0 | 가중평균 매입가 |
| positions.realized_profit | numeric(20,2) | DEFAULT 0 |  | 누적 실현손익 |
| portfolio_snapshots.account_id/snapshot_date | uuid/date | FK, UNIQUE pair |  | 일별 실제 계좌 평가 snapshot |
| portfolio_snapshots.total_assets/return_rate | numeric | NOT NULL |  | 현금 포함 총자산과 매입원가 기준 수익률 |
| strategy_target_weights.strategy_id/stock_code/effective_from | varchar | FK, UNIQUE version |  | 전략이 명시적으로 산출한 목표비중 버전 |
| strategy_target_weights.target_weight | numeric(9,8) | NOT NULL | 0~1 | 리밸런싱 계산용 비율 |
| rebalancing_decisions.id/account_id | uuid/uuid | PK/FK | account/created_at index | 실제 제안에 대한 판단 기록 |
| rebalancing_decisions.stock_code/action/decision | varchar | NOT NULL | BUY/SELL, ACCEPTED/HELD | 서버 제안과 사용자 선택 |
| rebalancing_decisions.current_weight/target_weight/recommended_amount | numeric | NOT NULL |  | 판단 당시 서버 산출값 snapshot |
| rebalancing_decisions.baseline_snapshot_date/total_assets | date/numeric | NULL |  | 판단 요청 시 재평가한 가격 기준일·총자산 |
| rebalancing_decisions.idempotency_key | varchar(100) | NOT NULL | UNIQUE(account,key) | 중복 판단 기록 방지 |
| orders.id | uuid | PK |  | 주문 ID |
| orders.account_id | uuid | FK virtual_accounts, NOT NULL | account/requested_at index | 주문 계좌 |
| orders.stock_code/side/order_type | varchar | NOT NULL | BUY/SELL, MARKET only | 주문 내용 |
| orders.quantity/requested_price | numeric(20,8)/numeric(20,4) | >0 / NULL | CHECK | 소수점 주문 수량/체결에 사용한 현재가 snapshot |
| orders.status | varchar(12) | NOT NULL | PENDING/FILLED/REJECTED/CANCELLED | 주문 상태 |
| orders.idempotency_key | varchar(100) | NOT NULL | UNIQUE(account,key) | 중복 요청 방지 |
| executions.id/order_id | bigint identity/uuid | PK/FK | order_id UNIQUE, RESTRICT | MVP 주문당 단일 체결 |
| executions.account_id | uuid | FK, NOT NULL | account/executed_at index | 체결 계좌 |
| executions.stock_code/side/quantity/price | varchar/varchar/numeric(20,8)/numeric | NOT NULL | 양수/CHECK | 소수점 수량을 포함한 체결 사실 |
| cash_ledger.id | bigint identity | PK |  | 원장 ID |
| cash_ledger.account_id | uuid | FK, NOT NULL | account/created_at index, RESTRICT | 계좌 |
| cash_ledger.transaction_type | varchar(30) | NOT NULL | INITIAL_DEPOSIT/BUY/SELL/ADJUSTMENT | 증감 이유 |
| cash_ledger.amount/balance_after | numeric(20,2) | NOT NULL | amount != 0, balance >= 0 | 증감액/결과 잔액 |
| cash_ledger.reference_type/id | varchar | NOT NULL | composite index | ACCOUNT/ORDER 추적 |

공통 시간은 `timestamptz`, DB server `now()`를 사용한다. `users`, `terms`, `user_agreements`, 가입 임시 관계는 기존 `20260816_0011`을 보존한다.

## Transaction 경계

시장가 체결 시 `virtual_accounts` 행을 `SELECT ... FOR UPDATE`로 잠그고 한 transaction에서 `orders → executions → positions → virtual_accounts.cash_balance → cash_ledger`를 처리한다. 하나라도 실패하면 rollback한다. `cash_balance`는 조회 snapshot, `cash_ledger`는 append-only 감사 이력이다.

## 보안·보존

- 개인정보는 기존 `users`에만 저장한다. 비밀번호는 bcrypt hash, CI/DI는 기존 encrypted/HMAC 정책을 따른다.
- 거래 테이블에는 개인정보가 없고 사용자 ownership은 계좌 FK를 통해 검증한다.
- 회원은 soft delete다. 사용자/계좌 및 거래 감사 FK는 RESTRICT, 포지션만 계좌 삭제 시 CASCADE이나 운영 API는 물리 삭제를 제공하지 않는다.
- 주문·체결·현금원장은 감사 대상이므로 물리 수정/삭제 API를 제공하지 않는다. 실제 법적 보존기간은 보안/컴플라이언스 담당 확정이 필요하다.
