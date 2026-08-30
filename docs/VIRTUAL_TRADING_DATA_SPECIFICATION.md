# 가상투자 데이터 명세서

Source of truth: `data/db/migrations/versions/20260823_0012_virtual_trading.py`부터 `20260827_0024_virtual_fund_operations.py`까지. PostgreSQL 17/Azure Database for PostgreSQL 호환.

| Table.Column | PostgreSQL Type | PK/FK/NULL/Default | Constraint/Index | 설명 |
| --- | --- | --- | --- | --- |
| strategies.id | varchar(30) | PK, NOT NULL |  | Frontend strategyId (`low/value/momentum`) |
| strategies.name/description | varchar(100)/text | NOT NULL |  | 표시명/설명 |
| strategies.risk_level | varchar(20) | NOT NULL | LOW/MEDIUM/HIGH | 위험도 |
| strategies.rebalance_cycle | varchar(30) | NOT NULL |  | 리밸런싱 주기 |
| strategies.rule_config | jsonb | NOT NULL |  | 모델과의 versionable interface |
| users.active_operation_mode | varchar(20) | NULL | AUTO/SEMI_AUTO | 현재 화면에서 사용하는 운용방식별 계좌 선택 |
| users.operation_mode_changed_at | timestamptz | NULL |  | 최초 활성화 또는 마지막 명시적 전환 시각 |
| virtual_accounts.id | uuid | PK |  | 가상계좌 ID |
| virtual_accounts.user_id/operation_mode | bigint/varchar(20) | FK users.id, NOT NULL | UNIQUE pair, RESTRICT | 사용자·AUTO/SEMI_AUTO별 계좌 |
| virtual_accounts.initial_cash/cash_balance | numeric(20,2) | NOT NULL | >=0 / >=0 | 최초 입금액/현재 cash snapshot |
| virtual_accounts.invested_principal | numeric(20,2) | NOT NULL, DEFAULT 0 | >=0 | 추가투자·출금 후 원금 기준액 |
| virtual_accounts.status | varchar(20) | DEFAULT ACTIVE | CHECK, index | ACTIVE/SUSPENDED/CLOSED |
| virtual_accounts.selected_strategy_id | varchar(30) | FK strategies.id, NULL | SET NULL | 선택 전략 |
| positions.id | bigint identity | PK |  | 포지션 ID |
| positions.account_id/stock_code | uuid/varchar(12) | FK, NOT NULL | UNIQUE pair, account index | 계좌별 종목 |
| positions.quantity | numeric(20,8) | NOT NULL | >=0 | 소수점 매매를 포함한 현재 보유수량 |
| positions.average_price | numeric(20,4) | NOT NULL | >0 | 가중평균 매입가 |
| positions.realized_profit | numeric(20,2) | DEFAULT 0 |  | 누적 실현손익 |
| portfolio_snapshots.account_id/snapshot_date | uuid/date | FK, UNIQUE pair |  | 일별 실제 계좌 평가 snapshot |
| portfolio_snapshots.total_assets/return_rate | numeric | NOT NULL |  | 현금 포함 총자산과 현재 투자원금 기준 수익률 |
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
| cash_ledger.transaction_type | varchar(30) | NOT NULL | INITIAL_DEPOSIT/DEPOSIT/ADDITIONAL_INVESTMENT/WITHDRAWAL/BUY/SELL/ADJUSTMENT | 증감 이유 |
| cash_ledger.amount/balance_after | numeric(20,2) | NOT NULL | amount != 0, balance >= 0 | 증감액/결과 잔액 |
| cash_ledger.reference_type/id | varchar | NOT NULL | composite index | ACCOUNT/ORDER 추적 |
| account_deposits.id/account_id/onboarding_id | uuid | PK/FK, NOT NULL | RESTRICT | 부족분 입금과 대상 계좌·온보딩 |
| account_deposits.amount/balance_after | numeric(20,2) | NOT NULL | >0 / >=0 | 정확한 부족분과 처리 후 잔액 |
| account_deposits.idempotency_key | varchar(100) | NOT NULL | UNIQUE(account,key) | 재시도 중복 입금 방지 |
| fund_operations.id/account_id | uuid/uuid | PK/FK, NOT NULL | account/created_at index, RESTRICT | 한 번의 가상 추가투자·출금 |
| fund_operations.operation_type/status/requested_amount/executed_amount | varchar/varchar/numeric/numeric | NOT NULL | UNIQUE(account,idempotency), CHECK | 작업 유형·완료 상태·요청/실행액 |
| fund_operations.principal/total_assets before/after | numeric | NOT NULL | >=0 | 작업 전후 원금과 총자산 snapshot |
| fund_operation_orders.operation_id/order_id | uuid/uuid | composite PK/FK | order UNIQUE | 자금 작업이 만든 주문과 배분 근거 |

공통 시간은 `timestamptz`, DB server `now()`를 사용한다. `users`, `terms`, `user_agreements`, 가입 임시 관계는 기존 `20260816_0011`을 보존한다.

`active_operation_mode`는 `virtual_accounts.operation_mode`를 덮어쓰는 값이 아니다. 사용자의 현재
조회 대상만 가리키며, 전환 시 두 계좌의 잔액·포지션·주문·체결·원장을 이동하거나 합치지 않는다.
`20260825_0021` upgrade는 가장 최근 완료 온보딩을 우선 사용하고, 완료 이력이 없으면 활성 계좌가
정확히 하나일 때만 backfill한다. 복수 계좌의 우선순위는 추측하지 않아 `NULL`로 남긴다.

`20260825_0020`의 운용방식별 복수 계좌, 0원 준비 계좌 또는 입금 이력이 생성된 뒤에는
`20260825_0019`가 해당 상태를 표현할 수 없으므로 자동 downgrade를 차단한다. 운영 rollback이
필요하면 백업 후 보존 계좌와 원장 변환 규칙을 명시한 별도 데이터 migration을 먼저 적용한다.

## Transaction 경계

시장가 체결 시 `virtual_accounts` 행을 `SELECT ... FOR UPDATE`로 잠그고 한 transaction에서 `orders → executions → positions → virtual_accounts.cash_balance → cash_ledger`를 처리한다. 추가투자·출금은 같은 잠금 아래 여러 주문과 `fund_operations`, 현재 원금까지 한 번에 commit하며 종목 하나라도 실패하면 전체 rollback한다. 원화 반올림 주문금액이 1원 미만이면 해당 종목 주문을 만들지 않는다. `cash_balance`는 조회 snapshot, `cash_ledger`는 append-only 감사 이력이다.

입출금은 실제 은행·증권계좌와 연결하지 않는다. `settlement_mode=VIRTUAL`인 내부 현금흐름이며 은행코드·계좌번호·예금주를 저장하거나 응답하지 않는다.

## 보안·보존

- 개인정보는 기존 `users`에만 저장한다. 비밀번호는 bcrypt hash, CI/DI는 기존 encrypted/HMAC 정책을 따른다.
- 거래 테이블에는 개인정보가 없고 사용자 ownership은 계좌 FK를 통해 검증한다.
- 회원은 soft delete다. 사용자/계좌 및 거래 감사 FK는 RESTRICT, 포지션만 계좌 삭제 시 CASCADE이나 운영 API는 물리 삭제를 제공하지 않는다.
- 주문·체결·현금원장은 감사 대상이므로 물리 수정/삭제 API를 제공하지 않는다. 실제 법적 보존기간은 보안/컴플라이언스 담당 확정이 필요하다.
