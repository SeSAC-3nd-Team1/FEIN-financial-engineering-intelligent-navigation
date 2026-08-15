# Data 저장 구조와 Docker 개발환경

한국 주식의 과거 분석, 백테스트 및 모델 학습 데이터를 수집하는 Python 3.13 환경입니다. 원본은 Azure Blob Storage, 정규화/서비스 데이터와 수집 상태는 PostgreSQL, 대용량 분석 산출물은 Blob Parquet에 저장합니다.

## 데이터 저장 원칙

```text
Raw        = Azure Blob Storage (JSON Lines + gzip)
Normalized = Azure PostgreSQL
Feature    = Azure Blob Storage (Parquet)
Service    = Azure PostgreSQL
Temporary  = Redis
Local      = 작은 Sample과 임시 cache
GitHub     = Code only
```

`raw` PostgreSQL schema에는 역사적인 이름 때문에 정규화 금융 table도 남아 있습니다. schema rename은 이번 범위에 포함하지 않으며, Raw 원문의 source of truth는 Azure Blob입니다.

## 디렉터리 구조

기존 `data/`와 `pipelines/`를 유지하면서 책임별 모듈을 추가했습니다.

```text
data/
├── collectors/             # 금융위/OpenDART/ECOS API 수집기(후속 구현)
├── loaders/                # ON CONFLICT UPSERT, DataFrame 적재
├── transforms/             # 전처리 및 Parquet export
├── features/               # Factor/재무비율 계산(후속 구현)
├── db/
│   ├── connection/         # 환경변수 기반 Engine/Session
│   ├── models/             # SQLAlchemy ORM
│   └── migrations/         # Alembic migration
├── notebooks/              # 탐색·검증 notebook
├── pipelines/              # 수집→정규화→적재 orchestration
├── scripts/                # DB 확인, 샘플 적재, 조회, export
├── storage/                # Blob SDK adapter, 경로, JSONL/gzip 직렬화
└── tests/                  # DB 구조·UPSERT·export 테스트
```

`data/raw/`, `data/processed/`, `data/exports/`는 임시 test/sample/notebook 경로이며 Git에서 제외됩니다. 영구 source of truth로 사용하지 않고 전체 Azure 데이터를 local volume에 복제하지 않습니다. 로컬 개발은 종목 10~50개, 최근 1~3개월 등 작은 sample만 사용합니다.

## Azure Blob 설정과 인증

```env
AZURE_STORAGE_ACCOUNT_NAME=stfeindata
AZURE_STORAGE_CONTAINER_RAW=raw
AZURE_STORAGE_CONTAINER_PROCESSED=processed
AZURE_STORAGE_CONTAINER_FEATURES=features
```

운영에서는 Managed Identity, 로컬에서는 `az login`을 통한 `DefaultAzureCredential`을 사용합니다. 실행 identity에는 Storage Account 범위의 `Storage Blob Data Contributor`만 부여합니다. Account Key, SAS, connection string은 commit하지 않습니다. Azurite test에 한해서만 `AZURE_STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true`를 local `.env`에 둘 수 있습니다.

## 공공데이터포털 실제 수집

저장소 루트 `.env`에 공공데이터포털의 일반 인증키(Decoding)를 저장합니다. 키를 코드, 명령 인자 또는 문서에 기록하지 않습니다.

```env
DATA_GO_KR_API_KEY=실제_키
```

환경변수를 Data 컨테이너에 적용하고 최신 migration을 실행합니다.

```bash
docker compose --profile data up -d --force-recreate data
docker compose exec data alembic upgrade head
```

기본 명령은 상장종목, 주식시세, 주가지수의 대표 operation을 한 페이지씩 시험 수집합니다.

```bash
docker compose exec data python scripts/collect_public_data.py \
  --date 2026-08-13 --rows 100 --max-pages 1
```

상장종목 전체 페이지를 먼저 적재한 뒤 같은 날짜의 주가와 지수를 적재합니다.

```bash
docker compose exec data python scripts/collect_public_data.py \
  --dataset stock_master --date 2026-08-13 --rows 1000 --max-pages 10

docker compose exec data python scripts/collect_public_data.py \
  --dataset stock_price --dataset market_index \
  --date 2026-08-13 --rows 1000 --max-pages 10
```

8개 데이터셋의 모든 52개 operation은 호출량과 이용조건을 확인한 뒤 명시적으로 실행합니다.

```bash
docker compose exec data python scripts/collect_public_data.py \
  --all-datasets --all-operations \
  --date 2026-08-13 --rows 100 --max-pages 1 --raw-only
```

5년치 최초 적재는 시작일과 종료일을 모두 포함하며, API 페이지마다 Blob과 DB를 확정하고
`raw.public_data_collection_checkpoint`에 진행 위치를 저장합니다. 같은 명령을 다시
실행하면 완료된 operation은 건너뛰고 미완료 operation의 다음 페이지부터 재개합니다.

```bash
docker compose exec data python scripts/collect_public_data.py \
  --all-datasets --all-operations --all-pages \
  --start-date 2021-08-14 --end-date 2026-08-13 \
  --rows 10000 --progress-every 25 --raw-only
```

`getStocIssuStat_V3`는 기간 조건 호출 시 공공데이터포털에서 타임아웃될 수 있습니다.
이 operation만 이미 적재된 주가 거래일을 기준으로 일자별 호출합니다. 일자마다
체크포인트를 기록하므로 연결 오류 후 같은 명령을 실행하면 이어서 수집합니다.

```bash
docker compose exec data python scripts/backfill_issuance_status.py \
  --start-date 2021-08-14 --end-date 2026-08-13 \
  --rows 10000 --progress-every 25
```

### 기존 5년을 10년으로 확장

이미 적재한 기간을 다시 호출하지 않고 부족한 과거 구간만 지정합니다. 다음 명령은
일반 51개 operation을 먼저 적재한 뒤, 확보된 주가 거래일을 이용해 발행현황을
일자별로 적재합니다. 두 단계 모두 Azure를 포함해 현재 `DATABASE_URL`이 가리키는
PostgreSQL에 직접 UPSERT하고 DB 체크포인트에서 재개합니다.

```bash
docker compose --env-file .env.azure run --rm data \
  python scripts/backfill_public_data_history.py \
  --start-date 2016-08-14 --end-date 2021-08-13 \
  --rows 10000 --progress-every 25
```

기존 범위가 `2021-08-14..2026-08-13`이면 위 구간을 더해 연속된 10년 범위가
됩니다. 다른 기준일에는 이미 저장된 범위와 겹치지 않는 부족 구간을 명시합니다.

수집 상태는 다음 쿼리로 확인합니다.

```bash
docker compose exec postgres psql -U app -d app -c \
  "SELECT dataset, operation, status, next_page, total_count, received_count
   FROM raw.public_data_collection_checkpoint
   ORDER BY dataset, operation;"
```

신규 Collector의 순서는 `API → Raw Blob → validation/normalize → PostgreSQL UPSERT → checkpoint`입니다. Blob 실패 시 DB transaction과 checkpoint를 시작하지 않습니다. 페이지의 record hash 집합으로 content-addressed 경로를 만들므로 DB commit 뒤 장애가 나도 재실행은 기존 Blob을 재사용합니다. 각 JSONL record의 `payloadHash`는 canonical JSON SHA-256이라 downstream 재처리 시 record 수준 dedupe가 가능합니다.

`raw.public_data_record`는 기존 24,070,779행 migration source로만 유지하며 신규 Collector는 더 이상 이 table에 INSERT하지 않습니다. 정규화 가능한 대표 operation은 기존 관계형 table에 계속 UPSERT합니다.

주식발행·배당 데이터는 공공누리 제2유형으로 안내되어 있으므로 상업 서비스 전환 전에 한국예탁결제원과 이용조건을 확인해야 합니다.

## PostgreSQL 스키마

Azure PostgreSQL에 실제 배포된 모든 업무 테이블의 통합 컬럼 명세와 데이터 현황은 [DATABASE_SPECIFICATION.md](../docs/DATABASE_SPECIFICATION.md)를 참고합니다.

회원가입 영구 데이터(`public.users`, `public.terms`, `public.user_agreements`)의 상세 설계, Redis 경계, seed와 통합 검증 방법은 [REGISTRATION_DB.md](REGISTRATION_DB.md)를 참고합니다.

| 테이블 | PK | FK | UPSERT UNIQUE |
| --- | --- | --- | --- |
| `raw.stock_master` | `stock_id` | - | `stock_code`, `isin` |
| `raw.stock_price_daily` | `price_id` | `stock_id → stock_master` | `(stock_id, trade_date, price_type)` |
| `raw.market_index_daily` | `market_index_id` | - | `(index_code, trade_date)` |
| `raw.stock_issuance` | `issuance_id` | `stock_id → stock_master` | `(stock_id, reference_date)` |
| `raw.financial_statement` | `financial_statement_id` | `stock_id → stock_master` | `(corp_code, business_year, report_code, fiscal_period, statement_scope)`, `receipt_number` |
| `raw.macro_indicator` | `macro_indicator_id` | - | `(indicator_code, observation_date, frequency)` |
| `raw.public_data_record` | `record_id` | - | `(dataset, operation, payload_hash)` |
| `raw.public_data_collection_checkpoint` | `checkpoint_id` | - | `(dataset, operation, range_start, range_end)` |
| `raw.data_object` | `data_object_id` | - | `(container, blob_path)` |
| `raw.public_data_migration_manifest` | `manifest_id` | - | `(source_table, dataset, operation, source_min_id, source_max_id)` |
| `public.users` | `id` | - | `user_id`, `email`, `ci_lookup_hash` |
| `public.terms` | `id` | - | `(term_code, version)` |
| `public.user_agreements` | `id` | `user_id → users`, `(term_code, term_version) → terms` | `(user_id, term_code, term_version)` |

금액은 최대 28자리 `NUMERIC`, 가격은 소수점/수정계수를 고려한 `NUMERIC`, 수량은 `BIGINT`, 비율은 부동소수 오차를 피하기 위해 `NUMERIC`을 사용합니다. 날짜/종목 및 날짜/지표 양방향 복합 인덱스를 두어 종목별 시계열과 특정 기간 전체 종목 학습 데이터를 모두 조회할 수 있습니다.

### Look-ahead Bias 방지

재무제표는 회계기간 `fiscal_period`, 결산 기준 `report_date`, 공시일 `disclosure_date`, 실제 사용 가능일 `available_date`를 구분합니다. 정정 공시나 수집 지연 정책을 반영해 `available_date`를 정하고 백테스트 쿼리에는 반드시 다음 조건을 포함합니다.

```sql
WHERE raw.financial_statement.available_date <= :backtest_date
```

주가는 `price_type`을 `unadjusted` 또는 `adjusted`로 저장하고 `adjustment_factor`를 선택적으로 기록합니다. 원천 API가 수정주가 이력을 제공하지 않는 동안에는 `unadjusted`만 적재하고, 액면분할·배당 등 corporate action 수집이 추가되면 동일 날짜의 `adjusted` 행을 별도로 UPSERT합니다.

향후 `processed.stock_factor_daily`는 `(stock_id, trade_date, factor_name, factor_version)`, `processed.financial_ratio`는 `(stock_id, fiscal_period, available_date, ratio_name, formula_version)` 형태의 유일키를 권장합니다. 계산 버전과 `available_date`를 포함해 재현성과 시점 정합성을 보장합니다.

## 실행과 접속

명령은 저장소 루트에서 실행합니다. Data profile은 기본 서비스(Frontend, Backend, PostgreSQL, Redis)와 Data 컨테이너를 함께 실행합니다.

```bash
docker compose --profile data up -d
docker compose exec data bash
```

최초 실행은 dependency와 이미지를 함께 빌드합니다.

```bash
cp .env.example .env
docker compose --profile data up -d --build postgres data
```

`.env`는 Git에서 제외됩니다. Compose 내부에서는 `postgres:5432`, 호스트 Python에서는 `localhost:${POSTGRES_PORT}`를 사용합니다. Azure Database for PostgreSQL 이전 시 코드 변경 없이 `DATABASE_URL`만 Azure 연결 문자열로 바꾸고 보통 `?sslmode=require`를 추가합니다.

## Migration과 연결 확인

```bash
docker compose exec data alembic upgrade head
docker compose exec data python scripts/check_db.py
docker compose exec data python scripts/db_inventory.py
# 대형 landing 테이블까지 전체 스캔하는 정확한 집계(운영 DB에서는 주의)
docker compose exec data python scripts/db_inventory.py --exact
```

Migration 상태와 롤백 SQL은 다음처럼 확인합니다.

```bash
docker compose exec data alembic current
docker compose exec data alembic history
docker compose exec data alembic downgrade -1
docker compose exec data alembic upgrade head
```

`alembic downgrade`는 데이터를 삭제할 수 있으므로 로컬 검증 DB에서만 실행합니다.

## DataFrame UPSERT

`loaders.upsert.upsert_dataframe`은 PostgreSQL `INSERT ... ON CONFLICT DO UPDATE`를 chunk 단위로 실행합니다. `conflict_columns`는 표의 UNIQUE 키와 동일해야 합니다. 한국어 금융위 컬럼을 사용하는 종목 Master/주가에는 `loaders.stocks`의 전용 loader가 컬럼명 변환과 `stock_code → stock_id` 연결을 처리합니다.

```python
with session_scope() as session:
    load_stock_master(session, master_df)
    load_stock_prices(session, price_df)
```

최초 전체 적재와 일별 증분 적재가 같은 loader를 사용하므로 재수집 시 중복 INSERT 대신 기존 행을 갱신합니다. 대량 최초 적재는 API 페이지별 또는 날짜 chunk별로 DataFrame을 나눠 메모리를 제한합니다.

## 샘플 적재와 조회

```bash
docker compose exec data python scripts/load_sample_data.py
docker compose exec data python scripts/load_sample_data.py  # 재실행해 UPSERT 확인
docker compose exec data python scripts/query_example.py
```

## Parquet export

모델 학습에는 DB 전체를 복제하지 않고 기간을 제한한 쿼리를 Parquet으로 내보냅니다.

```bash
docker compose exec data python scripts/export_parquet.py \
  --start 2026-08-01 \
  --end 2026-08-31 \
  --output exports/stock_prices_202608.parquet
```

기본 압축은 `zstd`이며 `exports/`는 Git에서 제외됩니다.

Azure `processed` container로 직접 보낼 때는 temporary directory를 거치며 완료 후 local 파일을 제거합니다.

```bash
docker compose exec data python scripts/export_parquet.py \
  --start 2026-08-01 --end 2026-08-31 --blob --schema-version 1
```

경로는 `processed/stock_price/year=YYYY/month=MM/*.parquet`이고 metadata에 생성 시각, source range, schema version, Git SHA를 기록합니다. Feature는 `features/<dataset>/version=<version>/<train|validation|test>/` 규칙을 사용합니다.

## Legacy Raw migration과 복구

Migration은 dataset/operation별 keyset cursor와 100~50,000행 chunk를 사용합니다. 전체 table을 메모리에 올리지 않으며 완료 chunk를 manifest에 commit하므로 같은 명령으로 이어서 실행할 수 있습니다.

```bash
PYTHONPATH=data python data/scripts/migrate_public_data_raw_to_blob.py \
  --chunk-size 50000

PYTHONPATH=data python data/scripts/verify_public_data_blob_migration.py --deep
```

검증은 전체/dataset별 건수, Blob size, gzip file SHA-256, JSONL 행 수, 각 payload SHA-256을 확인합니다. Blob upload 뒤 DB commit 전에 장애가 나면 content-addressed object를 다음 실행에서 재사용합니다. 기존 `raw.public_data_record`는 검증 직후 자동 삭제하지 않습니다. 팀 승인, Blob 접근/재처리 test, backup/restore 확인 후 read-only 유예 → backup → `TRUNCATE`를 별도 운영 작업으로 수행합니다.

## 보존·비용 정책

- Raw: immutable 원본. hash가 달라진 재수집은 별도 object이며 임의 수정하지 않습니다.
- Processed: 원천과 code version으로 재생성 가능하고 날짜 partition을 사용합니다.
- Features: model/formula/schema version과 split을 경로와 metadata에 남깁니다.
- 현재 프로젝트 기간에는 자동 Archive tier나 복잡한 lakehouse를 도입하지 않습니다.

대용량 immutable JSONB를 PostgreSQL primary storage와 index/backup에 반복 보관하는 대신 Blob의 저비용 object storage를 사용합니다. 관계형 제약과 조회가 필요한 정규화/서비스 데이터만 PostgreSQL에 유지합니다. 실제 금액은 region, transaction, redundancy, retention에 따라 달라지므로 문서에 고정하지 않습니다.

## 테스트

```bash
docker compose exec data pytest -q
docker compose exec data alembic check
```

`pytest`는 URL 정규화, ORM 제약/인덱스, PostgreSQL UPSERT SQL, DataFrame 변환, Parquet 생성을 검증합니다. 실제 PostgreSQL 통합 검증은 migration → sample load → query 명령 순서로 수행합니다.

컨테이너는 개발 중 계속 Running 상태를 유지합니다. 로컬 `data/`가 컨테이너 `/app`에 bind mount되므로 코드 변경이 바로 반영됩니다.

## Python Script 실행

```bash
docker compose exec data python scripts/example.py
docker compose exec data python pipelines/example.py
docker compose exec data python --version
```

## VS Code Dev Container

Host Python 없이 VS Code에서 Data Container의 Python 3.13으로 Script와 Notebook을 실행할 수 있습니다.

1. Docker Desktop을 실행합니다.
2. VS Code에 Microsoft의 **Dev Containers** Extension을 설치하고 저장소 루트를 엽니다.
3. Command Palette(macOS `Cmd + Shift + P`, Windows `Ctrl + Shift + P`)에서 `Dev Containers: Reopen in Container`를 실행합니다.
4. `SeSAC Data Dev`를 선택합니다. 선택 화면이 없으면 `Dev Containers: Open Folder in Container...`로 저장소 루트를 다시 엽니다.
5. 연결된 터미널에서 다음을 확인합니다.

   ```bash
   python --version
   which python
   ```

   Python 3.13.x와 `/usr/local/bin/python`이 출력되어야 합니다.
6. `.py` 파일은 Microsoft Python Extension의 **Run Python File** 버튼으로 실행합니다. Code Runner의 **Run Code**는 사용하지 않습니다.
7. `notebooks/`의 `.ipynb` 파일은 셀의 Run 버튼으로 실행합니다. 필요하면 `Select Kernel` → `Python Environments`에서 Container Python 3.13을 선택합니다.

VS Code 터미널은 Data Container의 shell이므로 다음처럼 직접 실행할 수도 있습니다.

```bash
python scripts/example.py
python pipelines/example.py
python -c "import ipykernel; print(ipykernel.__version__)"
```

Dev Container는 VS Code Window 단위로 연결됩니다. AI도 함께 작업한다면 저장소를 별도 창에서 열고 `SeSAC AI Dev`에 연결합니다.

## Dependency 추가

`data/requirements.txt`에 필요한 패키지와 버전을 추가한 뒤 이미지를 다시 빌드합니다.

```bash
docker compose build data
docker compose --profile data up -d
```

Dev Container를 사용 중이면 `data/requirements.txt` 수정 후 Command Palette의 `Dev Containers: Rebuild Container`로 이미지를 다시 빌드합니다. VS Code Notebook 실행에는 `ipykernel`을 사용하며, 브라우저 기반 JupyterLab은 포함하지 않습니다.

기존 CLI 방식도 그대로 지원합니다.

```bash
docker compose --profile data up -d
docker compose exec data python scripts/example.py
docker compose exec data python pipelines/example.py
```

## PostgreSQL / Redis 접근

Compose 네트워크에서는 `localhost` 대신 서비스명을 사용합니다. 연결 문자열은 `.env` 또는 `.env.example` 형식을 따르며 컨테이너에 `DATABASE_URL`, `REDIS_URL`로 전달됩니다.

- PostgreSQL: `postgres:5432`
- Redis: `redis:6379`

실제 Secret은 이미지, 소스 코드 또는 Compose 파일에 기록하지 않습니다.

## 상태 확인과 종료

```bash
docker compose ps
docker compose logs -f data
docker compose down
```

`docker compose down`은 컨테이너를 제거하지만 PostgreSQL과 Redis의 named volume 데이터는 유지합니다.
