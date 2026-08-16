# 금융 데이터 파이프라인 실행 Runbook

이 문서는 실제 Azure Blob 대용량 데이터 실행 담당자가 코드 수정 없이 파이프라인을 실행하기 위한 절차다.
한투 API는 이 파이프라인에 포함하지 않는다.

## 실행 범위

```text
Azure Blob raw
  ↓
Raw Profile
  ↓
Validation / Normalization
  ↓
Azure Blob processed v1
  ↓
Feature Engineering
  ↓
Azure Blob features v1
  ↓
Output Audit
```

Canonical Raw는 읽기만 하며 수정하거나 삭제하지 않는다.

## 0. 작업 브랜치 받기

프로젝트 루트에서 실행한다.

```cmd
git fetch origin && git switch feat/28-financial-data-pipeline && git pull origin feat/28-financial-data-pipeline
```

## 1. Docker data 이미지 준비

```cmd
docker compose --env-file .env.azure --profile data build data
```

코드는 `./data:/app` volume으로 연결되므로 이후 Python 코드 수정만으로 매번 이미지를 다시 build할 필요는 없다. `requirements.txt` 또는 `Dockerfile`이 바뀌었을 때만 다시 build한다.

## 2. Azure 로그인

기존 Azure CLI 로그인 volume이 유효하면 건너뛸 수 있다.

```cmd
docker compose --env-file .env.azure --profile data run --rm --no-deps data az account show
```

로그인이 필요하면:

```cmd
docker compose --env-file .env.azure --profile data run --rm --no-deps data az login --use-device-code
```

Shared Key는 사용하지 않는다. `AZURE_STORAGE_ACCOUNT_NAME` + Entra ID/DefaultAzureCredential 경로만 사용한다.

## 3. 실행 준비 점검

대용량 payload를 다운로드하지 않고 raw/processed/features container 접근과 8개 Raw dataset 존재만 확인한다.

```cmd
run-financial-pipeline.cmd check
```

성공 기준:

```text
PIPELINE CHECK OK ...
PIPELINE CHECK SUCCESS ...
```

실행 기록:

```text
data/reports/pipeline-runs/latest.json
data/reports/pipeline-runs/latest.md
```

## 4. 전체 실행

한 번에 실행하려면:

```cmd
run-financial-pipeline.cmd all
```

내부 순서:

```text
check
→ profile
→ processed
→ features
→ audit
```

### 터미널 진행률과 ETA

대용량 단계는 완료 시점만 출력하지 않고 현재 진행률과 예상 남은 시간을 지속적으로 출력한다.

Raw Profile 예시:

```text
PROFILE PROGRESS dataset=stock_price blobs=42/314 percent=13.4% rows=410,284 elapsed=00:01:52 eta=00:12:03
```

Processed 예시:

```text
PROCESSED PLAN dataset=stock_price partitions=64 pending=51 resume=13 expected_rows=2,810,000 compressed_bytes=...
PROCESSED PROGRESS dataset=stock_price partition=18/64 blob=2/4 rows=851,204/2,810,000 percent=30.3% speed=3,298rows/s elapsed=00:04:18 eta=00:09:52 current=getstockpriceinfo/2025-08
```

Feature 입력 로딩 예시:

```text
FEATURE LOAD PROGRESS dataset=stock_price operation=getstockpriceinfo files=18/60 percent=29.8% rows=1,021,553 elapsed=00:00:42 eta=00:01:39
```

ETA는 지금까지 처리한 행/압축 바이트 처리량을 기준으로 계산한다. 첫 몇 개 Blob에서는 표본이 적어 ETA가 크게 움직일 수 있으며, 처리량이 누적될수록 안정된다. Azure 네트워크 속도, Parquet 압축, 월별 컬럼 수 차이 때문에 실제 종료 시각과 완전히 일치하는 값은 아니다.

### Profile resume

`data/reports/raw-profile/{dataset}.json`이 이미 있으면 기본적으로 재사용한다.
Raw를 다시 전수 분석하고 싶을 때만 직접 CLI에서 `--refresh-profile`을 사용한다.

```cmd
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.run_financial_pipeline --stage profile --refresh-profile --schema-version 1 --feature-version 1
```

### Processed resume

기본 실행은 resume 방식이다.
동일 `schema=v1`의 월별 Parquet과 quality manifest가 모두 존재하고 계약이 일치하면 다음과 같이 건너뛴다.

```text
PROCESSED SKIP dataset=... operation=... year=... month=... rows=...
```

따라서 긴 실행이 중간에 멈췄다면 같은 명령을 다시 실행하면 완료된 월은 재처리하지 않는다.

강제 재생성은 필요한 경우에만 직접 CLI에서 `--overwrite`를 사용한다.

```cmd
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.run_financial_pipeline --stage processed --schema-version 1 --overwrite
```

## 5. 단계별 실행

전체 실행보다 상태를 단계별로 확인하고 싶다면 다음 순서로 실행한다.

```cmd
run-financial-pipeline.cmd profile
run-financial-pipeline.cmd processed
run-financial-pipeline.cmd features
run-financial-pipeline.cmd audit
```

Profile은 먼저 완료되어야 Processed를 만들 수 있고, Processed의 핵심 operation이 있어야 Features를 만들 수 있다.

## 6. Raw 분석 결과 확인

Profile 실행 후 다음 파일이 로컬에 생성된다.

```text
data/reports/raw-profile/INDEX.md
data/reports/raw-profile/disclosure.md
data/reports/raw-profile/financial_statement.md
data/reports/raw-profile/market_index.md
data/reports/raw-profile/security_product.md
data/reports/raw-profile/stock_dividend.md
data/reports/raw-profile/stock_issuance.md
data/reports/raw-profile/stock_master.md
data/reports/raw-profile/stock_price.md
```

각 dataset별 JSON도 같은 디렉터리에 생성된다. JSON은 후속 전처리 계약의 입력이며 Markdown은 사람이 확인하는 분석 기록이다.

Profile에는 다음이 기록된다.

- Blob/record/operation 수
- `basDt` 범위
- 컬럼 목록
- present/missing/null/empty
- 숫자/정수/날짜 변환 가능률
- cardinality
- 문자열 최대 길이
- 숫자 min/max
- 예시값

## 7. 모델링 산출물

Features v1은 다음 dataset을 만든다.

```text
model_stock_daily              training_ready
market_index_daily             training_ready
security_master_latest         reference_only
financial_snapshot             research_only_until_availability_date
financial_company_year_latest  research_only_until_availability_date
```

모델 담당자는 다음 문서를 먼저 읽는다.

```text
data/docs/MODELING_DATASET_CARD.md
data/docs/FEATURE_DICTIONARY.md
data/docs/FINANCIAL_DATA_PIPELINE.md
```

`financial_snapshot`, `financial_company_year_latest`는 OpenDART 실제 공시 availability timestamp가 붙기 전까지 가격 데이터와 자동 JOIN하지 않는다.

## 8. 최종 감사

전체 실행 또는 `audit` 단계가 성공하면 최신 실행 결과가 다음에 기록된다.

```text
data/reports/pipeline-runs/latest.json
data/reports/pipeline-runs/latest.md
```

최종 감사에는 다음이 포함된다.

- Processed dataset별 객체 수/record 수/bytes
- accepted/rejected 수
- rejection reason
- conversion error
- Feature dataset별 객체 수/record 수/bytes
- 모델 dataset status
- 최종 feature manifest
- look-ahead 정책

## 9. 실패했을 때

우선 다음 파일을 확인한다.

```text
data/reports/pipeline-runs/latest.md
```

실패한 단계부터 다시 실행한다.

```cmd
run-financial-pipeline.cmd processed
```

Processed는 완료 월을 재사용하므로 중간 실패 후 처음부터 2,400만 건을 다시 변환하지 않는다.

Features 실패 시:

```cmd
run-financial-pipeline.cmd features
```

최종 산출물이 생성된 뒤:

```cmd
run-financial-pipeline.cmd audit
```

으로 결과를 다시 확인한다.

## 10. Version 정책

현재 최초 전체 build는 다음을 사용한다.

```text
Processed schema version = v1
Feature version = v1
```

기존 v1의 의미나 컬럼을 변경해야 한다면 기존 데이터를 덮어써서 의미를 바꾸지 않고 v2를 만들어야 한다.
