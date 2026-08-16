# Raw Blob migration 결과 — Issue #16

## 실행 기준

| 항목 | 결과 |
| --- | --- |
| 실행일 | 2026-08-15 (Asia/Seoul) |
| 원본 | Azure PostgreSQL `raw.public_data_record` |
| 대상 | `stfeindata/raw/migration/` |
| 원본 DB 크기 | 16 GB |
| 원본 table 전체 크기 | 14 GB |
| 원본 row | 24,070,779 |
| Migration manifest | 525개, 실패 0개 |
| Migration Blob 압축 용량 | 2,169,539,858 bytes (약 2.02 GiB) |
| Raw container 전체 | 526 objects, 2,169,849,214 bytes |

Raw container 전체 값에는 migration 완료 후 실제 Collector E2E에서 만든 2,872행/309,356-byte Blob 1개가 포함된다.

## Dataset별 결과

| Dataset | PostgreSQL row | Blob record | Blob bytes | Files |
| --- | ---: | ---: | ---: | ---: |
| `disclosure` | 80,045 | 80,045 | 11,228,197 | 33 |
| `financial_statement` | 1,239,611 | 1,239,611 | 105,400,835 | 26 |
| `market_index` | 467,358 | 467,358 | 49,042,691 | 11 |
| `security_product` | 5,362,704 | 5,362,704 | 528,944,121 | 108 |
| `stock_dividend` | 71,681 | 71,681 | 4,331,523 | 2 |
| `stock_issuance` | 10,135,621 | 10,135,621 | 739,395,626 | 206 |
| `stock_master` | 3,211,333 | 3,211,333 | 309,878,428 | 66 |
| `stock_price` | 3,502,426 | 3,502,426 | 421,318,437 | 73 |
| **합계** | **24,070,779** | **24,070,779** | **2,169,539,858** | **525** |

## 무결성 검증

`verify_public_data_blob_migration.py --deep --samples-per-dataset 3` 결과:

- 전체 row count 일치
- 8개 dataset별 row count 일치
- 525개 Blob property size와 manifest size 일치
- 525개 Blob metadata checksum/count와 manifest 일치
- 525개 압축 object 전체 SHA-256 일치
- JSONL 전체 24,070,779행 parse 및 record count 일치
- 전체 24,070,779 payload canonical SHA-256 일치
- dataset별 무작위 Blob의 중간 record를 PostgreSQL payload/hash와 직접 비교
- failures: 0

## Azure E2E

2026-08-13 `stock_price/getStockPriceInfo`를 10,000행 page로 실제 수집했다.

| 검증 | 결과 |
| --- | --- |
| API 수신 | 2,872행 |
| Raw Blob | 1개, 309,356 bytes, gzip/JSONL 2,872행 |
| File SHA-256 | metadata와 일치 |
| 정규화 `stock_price_daily` | 해당 일자 2,872행 |
| Checkpoint | `complete`, `received_count=2872` |
| 동일 명령 재실행 | 완료 checkpoint로 skip |
| Legacy Raw row | 24,070,779 (증가 없음) |

같은 정규화 slice를 `processed/stock_price/year=2026/month=08/stock-prices-2026-08-13-2026-08-13.parquet`로 export했고 86,089 bytes, 2,872행, 9개 column을 실제로 다시 읽어 확인했다.

## Legacy table 상태와 정리 절차

`raw.public_data_record`는 삭제하지 않았고 기존 24,070,779행/14 GB를 그대로 유지한다. 신규 Collector에서는 write가 중단됐다.

팀 승인 뒤 별도 maintenance change로 다음을 수행한다.

1. 팀원이 Managed Identity/Azure CLI로 Raw Blob을 읽을 수 있는지 확인한다.
2. 대표 Blob에서 정규화 재처리/restore rehearsal을 수행한다.
3. Azure PostgreSQL PITR/backup 시점과 restore 절차를 확인한다.
4. 합의한 read-only 유예 기간을 지킨다.
5. backup을 보존한 뒤 `TRUNCATE raw.public_data_record` 여부를 승인받는다.
6. 실제 반환 용량은 PostgreSQL storage/autogrow 정책을 고려해 별도 점검한다.

이번 작업에서는 데이터 손실 가능성이 있는 `DROP`, `TRUNCATE`, 대량 `DELETE`를 실행하지 않았다.
