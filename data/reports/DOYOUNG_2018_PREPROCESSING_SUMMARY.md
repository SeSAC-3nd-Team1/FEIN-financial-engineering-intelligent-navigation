# 정도영 2018 모델 데이터 전처리 결과

- 요청 기간: 2018-01-01 ~ 2026-08-26
- Processed schema: v2
- Feature version: v2

## Dataset

| dataset | layer | status | rows | path |
|---|---|---|---:|---|
| `model_stock_daily` | features | `training_ready` | 5,238,800 | `model_stock_daily/version=v2/` |
| `market_index_daily` | features | `training_ready` | 260,621 | `market_index_daily/version=v2/` |
| `macro_daily` | features | `training_ready_pit_conservative` | 2,129 | `macro_daily/version=v2/` |
| `opendart_disclosures` | processed | `event_ready` | 941,084 | `opendart_disclosures/operation=disclosure_market/schema=v2/` |
| `opendart_financial_accounts` | processed | `research_only_until_receipt_linkage` | 2,074,575 | `opendart_financial_accounts/operation=financial_multi/schema=v2/` |

## 안전 제한

- OpenDART 재무는 접수번호·접수일 연결 전까지 가격 학습 데이터에 JOIN하지 않는다.
- 현재 KRX 가격은 corporate action 조정계열이 아니므로 배당·분할 이벤트 보강이 필요하다.
- `target_*` 컬럼은 Feature 입력에서 제외한다.

## 2018 coverage 미확보로 제외

- `foreign_institutional_flow`
- `vix_vkospi`
- `sox_overseas_sector_index`
- `sp500_nasdaq`
- `historical_transaction_cost_and_spread`
