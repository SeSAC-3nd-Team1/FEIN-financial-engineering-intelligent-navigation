# Raw Profile Index

> Azure Blob canonical Raw 전수 프로파일링 결과. JSON은 기계 판독용 전체 통계이고 Markdown은 사람이 검토하기 위한 상세 리포트다.

| dataset | operations | blobs | records | compressed bytes |
|---|---:|---:|---:|---:|
| `disclosure` | 33 | 1,749 | 80,045 | 13,434,579 |
| `financial_statement` | 3 | 1,030 | 1,239,611 | 109,089,426 |
| `market_index` | 3 | 191 | 467,358 | 49,158,645 |
| `security_product` | 3 | 288 | 5,362,704 | 529,061,472 |
| `stock_dividend` | 1 | 2 | 71,681 | 4,331,523 |
| `stock_issuance` | 4 | 528 | 10,135,621 | 739,636,980 |
| `stock_master` | 1 | 126 | 3,211,333 | 309,906,739 |
| `stock_price` | 4 | 314 | 3,505,298 | 421,835,692 |

- total datasets: **8**
- total operations: **52**
- total blobs: **4,228**
- total records: **24,073,651**

## 결측 통계 해석

- `missing`: 해당 payload에 key 자체가 없는 행 수
- `null`: JSON null 값인 행 수
- `empty`: 빈 문자열인 행 수
- `null_or_empty_rate`: 존재하는 필드 값 중 null/빈 문자열 비율
- 높은 결측률은 곧 오류라는 뜻이 아니며 operation의 구조적 특성과 함께 해석한다.

기준 실행: GitHub Actions `31932890997` (2026-08-16).
