# Data

데이터 수집, Azure Blob Raw 저장, Raw profiling, Processed Parquet, 모델용 Features, PostgreSQL migration과 화면 조회용 정제 데이터 적재를 담당한다.

## 현재 구조

```text
Public Data API / KRX OPEN API
  ↓
Azure Blob raw (JSONL.gz)
  ↓
Raw Profile / Validation / Normalization
  ↓
Azure Blob processed (Parquet)
  ↓
Feature Engineering
  ↓
Azure Blob features (Parquet)
```

금융 Raw/Processed/Features 파이프라인은 PostgreSQL을 경유하지 않는다. PostgreSQL은 회원가입·가상투자 같은 관계형 서비스 데이터와 KRX/OpenDART의 화면 조회용 정제 결과만 담당한다.

## 현재 원칙

- API Raw 원문 source of truth: Azure Blob Storage
- Canonical Raw는 immutable
- PostgreSQL에 금융 Raw JSON 전체를 중복 저장하지 않음
- Processed/Features는 Raw에서 재생성 가능
- Azure Storage 인증은 Entra ID/DefaultAzureCredential 우선
- Shared Key 기반 실제 Azure connection string 사용 금지
- 숫자처럼 보이는 종목코드/법인번호/ID는 문자열 보존
- 결측값을 임의의 0/평균값으로 일괄 보정하지 않음
- 재무 `base_date`는 실제 공개일이 아니므로 availability timestamp 확보 전 가격과 PIT JOIN 금지

## 코드 주석 규칙

`data/` 영역은 데이터 의미와 운영 제약을 팀원이 빠르게 이해할 수 있도록 한국어 주석과 도큐스트링을 사용한다. 세부 규칙은 `data/AGENTS.md`를 따른다.

- 모듈, 주요 함수, 클래스 설명은 한국어
- `basDt`, hash 기반 멱등성, transaction, feature window처럼 실수하기 쉬운 규칙은 왜 필요한지 설명
- 단순 대입 등 코드만으로 명확한 부분에는 과도한 주석을 추가하지 않음
- API 필드명, 함수/변수명, SQL 식별자, 환경변수, Azure 서비스명과 로그 키는 영문 유지

## 디렉터리

```text
data/
├─ AGENTS.md
├─ Dockerfile.db-init  # Alembic + 약관 seed 전용 경량 이미지
├─ collectors/          # data.go.kr/KRX/OpenDART/ECOS API client/config
├─ db/
│  ├─ connection/       # PostgreSQL 연결
│  ├─ migrations/       # Alembic history
│  └─ models/           # 관계형 서비스/시장 조회용 ORM
├─ docs/                # 금융 pipeline/model 문서
├─ features/            # 모델용 Dataset/Feature 생성
├─ loaders/             # PostgreSQL UPSERT repository
├─ notebooks/           # 분석 Notebook 공간
├─ processing/          # Raw → Processed 정규화/품질/계약
├─ reports/
│  └─ raw-profile/      # 기계용 JSON + 사람용 Markdown
├─ scripts/
│  ├─ collect_public_data.py
│  ├─ sync_krx.py
│  ├─ profile_raw_data.py
│  ├─ run_financial_pipeline.py
│  ├─ audit_model_data_outputs.py
│  ├─ audit_raw_partition_dates.py
│  ├─ check_db.py
│  ├─ init_local_db.py
│  ├─ seed_investment_terms.py
│  ├─ seed_signup_terms.py
│  └─ verify_signup_schema.py
├─ storage/             # Blob auth/path/Raw serialization
├─ transforms/          # 범용 분석 export helper
└─ tests/
```

## Raw Blob

Canonical layout:

```text
raw/
├─ data-go-kr/{dataset}/operation={operation}/year=YYYY/month=MM/{sha256}.jsonl.gz
└─ krx/{dataset}/operation={operation}/year=YYYY/month=MM/{sha256}.jsonl.gz
```

`payload.basDt`가 Raw partition/filter의 권위 있는 기준일이다. `day=DD`, `migration/` prefix, page-number filename은 신규 canonical 경로에서 사용하지 않는다.

Raw 수집 예시:

로컬 수집은 저장소 루트 `.env`의 `DATA_GO_KR_API_KEY`를 사용한다. 별도 `.env.azure` 파일이나 `--env-file` 옵션은 사용하지 않는다.

```bash
docker compose --profile data run --rm --no-deps data python -m scripts.collect_public_data --dataset stock_price --date 2026-08-16 --all-pages --rows 10000
```

최소 5년 백필과 실제 Raw 월 보유기간 감사:

```bash
docker compose --profile data run --rm --no-deps data python -m scripts.collect_public_data --dataset stock_price --dataset market_index --history-years 5 --all-pages --rows 10000
docker compose --profile data run --rm --no-deps data python -m scripts.audit_raw_coverage --minimum-years 5
```

매일 자동 증분 수집은 `.github/workflows/raw-daily-collection.yml`에서 15:30 KST에 실행한다.
공휴일과 지연 갱신을 보완하기 위해 최근 7일을 일자별로 확인하며, GitHub Actions Secret
`DATA_GO_KR_API_KEY`와 기존 Azure OIDC Secret/Blob 쓰기 권한이 필요하다.

장기 범위 요청이 시간 초과되는 operation은 `scripts.backfill_public_data_by_date`로 날짜별
병렬 백필한다. 개별 날짜가 완료될 때마다 Raw Blob이 남으므로 일부 요청 실패 후에도 성공
날짜를 다시 잃지 않는다.

데이터 목록, 출처, 우선순위, 현재 관측 범위와 후속 source는
[`docs/RAW_DATA_CATALOG.md`](docs/RAW_DATA_CATALOG.md)를 기준으로 한다.

## KRX OPEN API 동기화

승인된 7개 endpoint에서 KOSPI·KOSDAQ 종목기본정보와 일별 OHLCV, KOSPI·KOSDAQ·KRX 지수를 수집한다. `AUTH_KEY` header와 `basDd=YYYYMMDD` query를 사용하며, 서비스 계약인 숫자 6자리 종목코드는 선행 0을 포함한 문자열로 보존한다. 영문 혼합 단축코드는 현재 StockDetail·가상거래 계약 밖이므로 해당 행만 제외하고, 종가가 비어 있는 보조 지수도 저장하지 않는다. 원문은 필터 전 상태로 `raw/krx/...`에 불변 저장하고 화면 조회에 필요한 정제 결과만 `market_stocks`, `market_stock_prices`, `market_indices`에 멱등 UPSERT한다.

```bash
docker compose --profile migration run --rm --no-deps db-init
docker compose --profile data run --rm --no-deps data python -m scripts.sync_krx --date 2026-08-24
```

Migration 직후 5년 차트에 필요한 과거 시세를 초기 적재할 때는 양끝을 포함하는 범위 백필을 실행한다. 범위에서는 거래가 없는 주말을 건너뛰고 날짜별 transaction으로 커밋하므로, 중간 실패 시 같은 명령을 다시 실행해 멱등 재개할 수 있다. GitHub Actions의 수동 실행에서도 `start_date`와 `end_date`를 함께 입력할 수 있다.

```bash
docker compose --profile data run --rm --no-deps data python -m scripts.sync_krx --start-date 2021-08-24 --end-date 2026-08-24
```

GitHub Actions의 Azure OIDC나 Raw Blob 권한 없이 화면 조회용 PostgreSQL만 로컬에서
초기 백필하려면 저장소 루트의 Windows 실행기를 사용한다. `.env`의 `DATABASE_URL`과
`KRX_AUTH_KEY`, 실행 중인 Docker Desktop만 필요하다. 기본 종료일은 실행 당일이고 시작일은
그로부터 5년 전으로 동적 계산한다. 완료 후 종목 가격과 시장 지수의 기간 경계, 평일 대비
거래일 밀도, 내부 최대 공백을 자동 검증한다. 날짜별 UPSERT가 멱등이므로 중간에 중단되면
같은 명령을 다시 실행할 수 있다.

```cmd
run-krx-backfill.cmd
```

다른 범위는 PowerShell 인자로 지정한다.

```powershell
.\run-krx-backfill.ps1 -StartDate 2021-08-24 -EndDate 2026-08-24
```

이 로컬 실행기는 의도적으로 `--skip-blob`을 사용하므로 PostgreSQL serving table만
갱신하고 canonical Raw Blob은 만들지 않는다. Raw 보존이 필요한 정기 운영 수집은 Azure
OIDC가 설정된 `KRX Daily Sync` workflow를 사용한다.

StockDetail 기간 차트와 Strategy Backtest는 동일한 `market_stock_prices`, `market_indices`를 사용한다. 백테스트 요청 기간 이전에 factor lookback 최대 126거래일이 추가로 필요하므로 운영 초기 백필 시작일은 화면에서 허용할 최소 시작일보다 최소 260일 앞서 잡는다. 저장되지 않은 기간은 Backend가 unavailable로 응답하며 합성 곡선으로 대체하지 않는다.

로컬 parser와 PostgreSQL 적재만 진단할 때는 `--skip-blob`을 사용할 수 있으나 운영 동기화에서는 사용하지 않는다. `.github/workflows/krx-daily-sync.yml`은 평일 18:30 KST에 실행하며 GitHub Actions Secret `KRX_AUTH_KEY`, `DATABASE_URL`과 기존 Azure OIDC Secret/Blob 쓰기 권한이 필요하다. 이 workflow는 공용 DB migration을 자동 적용하지 않으므로 `20260824_0016`이 승인·반영된 뒤 migration 담당자가 먼저 `db-init`을 실행해야 한다. 휴장일처럼 KRX가 빈 목록을 반환하면 임의 값을 생성하지 않는다.

## 금융 데이터 파이프라인

Windows CMD, 프로젝트 루트 기준:

```cmd
run-financial-pipeline.cmd check
run-financial-pipeline.cmd profile
run-financial-pipeline.cmd processed
run-financial-pipeline.cmd features
run-financial-pipeline.cmd audit
```

전체 실행:

```cmd
run-financial-pipeline.cmd all
```

직접 Python CLI:

```bash
docker compose --profile data run --rm --no-deps data python -m scripts.run_financial_pipeline --stage all --schema-version 1 --feature-version 1
```

### Raw Profile

```text
data/reports/raw-profile/INDEX.md
data/reports/raw-profile/{dataset}.json
data/reports/raw-profile/{dataset}.md
```

JSON은 Processed 타입 계약 입력으로 실제 코드가 사용한다. Markdown은 사람이 확인하는 리포트다. 둘은 중복 파일이 아니라 역할이 다르다.

### Processed

```text
processed/{dataset}/operation={operation}/schema=v1/year=YYYY/month=MM/part-00000.parquet
processed/_quality/{dataset}/operation={operation}/schema=v1/year=YYYY/month=MM/manifest.json
```

### Features

```text
features/{dataset}/version=v1/year=YYYY/month=MM/part-00000.parquet
features/_manifests/model-datasets/version=v1/manifest.json
```

## PostgreSQL

현재 구현 기준 Alembic head는 `20260825_0020`이다.

현재 membership/registration 관계:

```text
public.users
public.terms
public.user_agreements
public.registration_sessions
public.registration_agreements
public.companies
public.company_financial_accounts
public.company_financials
public.company_disclosures
public.market_stocks
public.market_stock_prices
public.market_indices
public.alembic_version
```

과거 금융/API PostgreSQL `raw`, `processed` schema는 retire되었으며 정상 금융 batch 실행에는 필요하지 않다.

Migration 적용(Local/Azure 공통):

```bash
docker compose --profile migration run --rm --no-deps db-init
```

`db-init`은 Alembic migration과 `dev-` 약관 seed를 PostgreSQL advisory lock 안에서 적용한다. 공용 Azure DB에서 여러 개발자가 동시에 실행해도 초기화는 직렬화되며, 적용된 revision과 같은 code/version 약관은 건너뛴다. 일반 `docker compose up`은 이를 자동 실행하지 않는다. migration 담당자가 임시/CI PostgreSQL 검증과 `develop` 반영을 마친 뒤 공용 Azure DB에 명시적으로 실행한다. 승인된 version의 명시적 seed는 다음과 같다.

```bash
docker compose --profile migration run --rm --no-deps db-init
docker compose run --rm data python -m scripts.seed_signup_terms --version dev-20260823 --effective-at 2026-08-23T00:00:00+09:00
```

두 명령 모두 동일 code/version을 다시 실행해도 중복 insert하지 않는다. 운영 환경에서는 `dev-` 기본값을 사용하지 않는다.

DB 확인:

```bash
docker compose run --rm --no-deps data python -m scripts.check_db
```

Azure 연결과 전체 공용 개발 절차는 [`docs/AZURE_POSTGRESQL_DEV.md`](../docs/AZURE_POSTGRESQL_DEV.md)를 따른다.

## OpenDART 수집

`.env`에 실제 key를 넣고 Git에는 커밋하지 않는다.

```env
OPENDART_API_KEY=
OPENDART_TIMEOUT_SECONDS=10
```

Migration 적용 후 corp code를 먼저 동기화한다. 모든 종목코드는 숫자가 아니라 문자열로
저장되므로 `005930`의 선행 0이 유지된다.

```bash
docker compose --profile migration run --rm --no-deps db-init
docker compose --profile data run --rm --no-deps data python -m scripts.sync_opendart corp-codes
docker compose --profile data run --rm --no-deps data python -m scripts.sync_opendart company --stock-code 005930
docker compose --profile data run --rm --no-deps data python -m scripts.sync_opendart companies --limit 100
docker compose --profile data run --rm --no-deps data python -m scripts.sync_opendart financials --stock-code 005930 --year 2025 --report-code 11011
docker compose --profile data run --rm --no-deps data python -m scripts.sync_opendart disclosures --stock-code 005930 --limit 20
```

공시 `--limit`이 100을 초과하면 OpenDART `page_no`/`total_page`를 따라 여러 페이지를
수집하며, 요청한 건수까지만 PostgreSQL에 적재하고 각 HTTP 페이지 원문은 모두 별도 Raw
Blob으로 저장한다.

로컬 parser/DB 동작만 진단하고 Azure Blob 업로드를 생략할 때는 최상위 option을 subcommand
앞에 둔다: `python -m scripts.sync_opendart --skip-blob corp-codes`. 운영 수집에서는 이
option을 사용하지 않는다. 수집 주기는 corp code 하루 1회 이하, 재무는 분기·사업보고서
제출 후, 공시는 scheduler에서 작은 조회 기간으로 증분 실행하는 것을 권장한다.

Raw 경로와 테이블 명세는 각각 `data/docs/RAW_DATA_CATALOG.md`,
`docs/DATABASE_SPECIFICATION.md`를 따른다.

## 한국은행 ECOS 거시경제 데이터

`.env`에 `ECOS_API_KEY`를 설정한 뒤 2018년부터 기준금리, 원/달러 환율, CPI,
국고채 3년·10년을 수집한다. 백필과 증분 실행은 동일 CLI를 사용하며 Raw는 원문을
content-addressed JSONL.gz로 보존한다.

```bash
docker compose --profile data run --rm --no-deps data python -m scripts.run_ecos_pipeline --stage raw --start-date 2018-01-01 --validate-metadata
docker compose --profile data run --rm --no-deps data python -m scripts.run_ecos_pipeline --stage all --incremental
docker compose --profile data run --rm --no-deps data python -m scripts.run_ecos_pipeline --stage raw --series base_rate --start-date 2026-01-01
docker compose --profile data run --rm --no-deps data python -m scripts.run_ecos_pipeline --stage processed
docker compose --profile data run --rm --no-deps data python -m scripts.run_ecos_pipeline --stage features
docker compose --profile data run --rm --no-deps data python -m scripts.run_ecos_pipeline --stage audit
```

API key가 없는 환경에서도 parser, 품질 규칙, PIT feature 단위 테스트는 실행되며 실제
endpoint smoke test만 skip된다. Blob은 Azure CLI/Managed Identity 기반 Entra ID로 인증한다.

## 모델 Raw 장기 수집

KRX·ECOS·OpenDART 모델 원본은 PostgreSQL을 거치지 않고 아래 한 명령으로 2018-01-01부터
최신일까지 Azure Blob `raw` 컨테이너에 구축한다.

```bash
docker compose --profile data run --rm data python -m scripts.collect_model_raw
```

수집기는 실제 Blob partition과 `_manifests/model_raw_coverage.json`을 교차검증해 누락 구간만
호출한다. KRX 날짜, ECOS 시계열×월, OpenDART 회사 100개/공시 월 구간을 bounded worker로
처리하며 성공 partition만 checkpoint한다. 같은 범위를 재실행하면 provider를 다시 호출하지
않는다. 한 달 성능 측정은 다음처럼 실행한다.

```bash
docker compose --profile data run --rm data python -m scripts.collect_model_raw \
  --benchmark --start-date 2026-08-01 --end-date 2026-08-24
```

결과는 `reports/MODEL_RAW_COLLECTION_SUMMARY.{json,md}`와
`docs/DOYOUNG_MODEL_DATA_INVENTORY.md`에 기록된다. OpenDART 재무를 가격과 결합할 때는
결산일이 아니라 실제 공시 `rcept_dt` 이후에만 사용할 수 있다.

## 2018 모델 데이터 전처리

2018-01-01부터 실제 Raw coverage가 확인된 KRX·ECOS·OpenDART만 schema/feature v2로
전처리하고 범위를 감사한다. 외국인·기관 수급, VIX/VKOSPI, SOX처럼 2018 coverage가 없는
데이터를 임의 생성하거나 섞지 않는다.

```bash
docker compose --profile data run --rm --no-deps data \
  python -m scripts.preprocess_model_2018
```

KRX는 `model_stock_daily`, `market_index_daily`, ECOS는 point-in-time 지연 정책을 적용한
`macro_daily` Features를 만든다. OpenDART 공시 목록은 실제 `rcept_dt` 기반 이벤트
Processed를 만들지만, 재무 API에는 접수일 연결 정보가 없으므로
`point_in_time_join_ready=false`로 유지하고 가격 학습 데이터와 자동 JOIN하지 않는다.
월별 Raw 경로 fingerprint가 같으면 OpenDART Processed를 재생성하지 않는다.

성공 결과는 Azure Features의
`_manifests/doyoung-2018/version=v2/manifest.json`과 로컬
`reports/DOYOUNG_2018_PREPROCESSING_SUMMARY.{json,md}`에서 확인한다.

회원가입 상세 구현 가이드는 `data/REGISTRATION_DB.md`를 본다.

## 테스트

```bash
docker compose --profile data run --rm --no-deps data python -m pytest tests -q
```

## 주요 문서

- `data/docs/FINANCIAL_DATA_PIPELINE.md`
- `data/docs/FINANCIAL_PIPELINE_RUNBOOK.md`
- `data/docs/MODELING_DATASET_CARD.md`
- `data/docs/FEATURE_DICTIONARY.md`
- `data/docs/RAW_DATA_CATALOG.md`
- `docs/DATA_ARCHITECTURE.md`
- `docs/DATA_LAYER_OPERATIONS.md`
- `docs/DATABASE_SPECIFICATION.md`
