# Data Layer Operations

## 1. Layer contract

| Layer | Storage | Role | Rebuildable |
|---|---|---|---|
| Raw | Azure Blob `raw` | API 원문 source of truth | No |
| PostgreSQL | Azure Database for PostgreSQL | 서비스/정규화 데이터, checkpoint, searchable metadata | Yes, from Raw where applicable |
| Processed | Azure Blob `processed` | 분석 친화적 monthly Parquet | Yes |
| Features | Azure Blob `features` | 버전 관리된 분석/ML feature Parquet | Yes |

## 2. Azure Blob authentication

실제 Azure Storage는 `AZURE_STORAGE_ACCOUNT_NAME` + `DefaultAzureCredential`을 사용한다.
Shared Key 또는 실제 Azure connection string 인증은 코드에서 거부한다.
`UseDevelopmentStorage=true`는 로컬 Azurite에만 허용한다.

Docker 개발 환경에서는 data 이미지에 Azure CLI가 포함되어 있으며,
Compose의 `azure_cli_data` named volume이 `/root/.azure`를 영속화한다.

```bash
docker compose --env-file .env.azure --profile data build data
docker compose --env-file .env.azure --profile data run --rm --no-deps data az login --use-device-code
```

## 3. Raw Blob catalog reconciliation

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.reconcile_raw_blob_catalog --expected-minimum 4228
```

기본은 dry-run이다. 실제 반영은 `--apply`를 추가한다.
canonical `data-go-kr/.../year=YYYY/month=MM/*.jsonl.gz`만 catalog 대상으로 인정하며,
Blob에서 사라진 legacy catalog row는 삭제하지 않고 `status=deleted`로 표시한다.

## 4. Legacy PostgreSQL Raw retirement

`raw.public_data_record`는 과거 Raw JSONB landing table이며, Raw source of truth를 Blob으로
전환한 뒤 전수 검증을 거쳐 비운다.

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.retire_legacy_raw_data --truncate-after-verify --expected-blob-count 4228
```

검증 항목:
- canonical Raw Blob compressed SHA-256
- 모든 payload hash 재계산
- 모든 historical `legacy.recordId` ↔ SQL `record_id` 전수 대조
- dataset/operation/payload_hash 일치
- Blob catalog path parity
- SQL 변경 감지 후 destructive 작업 차단

성공 시 `raw.public_data_record`의 row만 TRUNCATE하고 테이블 구조는 유지한다.

## 5. Financial PostgreSQL rebuild gate

금융 SQL을 Blob Raw에서 재구축하기 전에 SQL에만 남은 API 원문이 없는지 먼저 보존한다.
회원가입/약관 DB는 이 작업에서 절대 삭제하지 않는다.

보존 대상:
- `public.users`
- `public.terms`
- `public.user_agreements`
- `public.alembic_version`

금융/API reset 대상:
- `raw.stock_master`
- `raw.stock_price_daily`
- `raw.market_index_daily`
- `raw.stock_issuance`
- `raw.financial_statement`
- `raw.macro_indicator`
- `raw.public_data_record`
- `raw.public_data_collection_checkpoint`
- `raw.data_object`
- `raw.public_data_migration_manifest`

실행:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.rebuild_financial_sql --sync-missing-to-blob --reset-after-sync
```

동작 순서:
1. 회원가입 테이블 row count를 snapshot한다.
2. 정규화 금융 테이블의 API-origin `source_payload`를 SHA-256으로 인덱싱한다.
3. 관련 canonical Raw Blob을 전수 스캔해 이미 보존된 payload를 제거한다.
4. SQL에만 있는 API payload가 있으면 canonical monthly Raw Blob에 추가한다.
5. 새 Blob을 다시 읽어 checksum과 payload hash를 검증한다.
6. mapping되지 않은 non-null `source_payload`가 있으면 reset을 거부한다.
7. untouched table이 금융 reset table을 FK로 참조하면 reset을 거부한다.
8. `CASCADE` 없이 금융/API 테이블만 `TRUNCATE ... RESTART IDENTITY` 한다.
9. 회원가입 테이블 row count가 그대로인지 확인하고, reset 대상은 모두 0행인지 검증한다.

현재 `stock_issuance`, `financial_statement`, `macro_indicator`의 1행은
`scripts.load_sample_data`가 만든 개발 샘플이며 API Raw 원문이 아니다.

## 6. Processed monthly Parquet

PostgreSQL 정규화 데이터가 다시 구성된 뒤 monthly Parquet을 생성한다.

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.export_processed_monthly --dataset stock_price --start 2021-08-14 --end 2026-08-13 --schema-version 1
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.export_processed_monthly --dataset market_index --start 2021-08-14 --end 2026-08-13 --schema-version 1
```

경로:

```text
processed/{dataset}/schema=vN/year=YYYY/month=MM/part-00000.parquet
```

기존 object는 `--overwrite` 없이는 덮어쓰지 않는다.

## 7. Stock-price features

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.build_stock_price_features --start 2021-08-14 --end 2026-08-13 --processed-schema-version 1 --feature-version 1
```

경로:

```text
features/stock_price/version=vN/year=YYYY/month=MM/part-00000.parquet
```

종목별 rolling window와 warm-up을 사용해 cross-stock leakage를 방지한다.
