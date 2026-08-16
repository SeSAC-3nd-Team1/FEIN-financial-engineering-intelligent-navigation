# 금융 데이터 파이프라인 실행 Runbook

이 문서는 실제 Azure Blob 대용량 데이터 실행 담당자가 코드 수정 없이 현재 금융 데이터 파이프라인을 실행하기 위한 절차다. KIS는 이 오프라인 학습 파이프라인 범위에 포함하지 않는다.

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

## 0. 기준 브랜치 받기

프로젝트 루트에서 실행한다.

```cmd
git fetch origin
git switch develop
git pull origin develop
```

특정 이슈 브랜치에서 검증 중이라면 해당 PR의 base/head와 목적을 확인한 뒤 실행한다. 일반 운영 문서는 `develop`을 기준으로 한다.

## 1. Docker data 이미지 준비

```cmd
docker compose --env-file .env.azure --profile data build data
```

코드는 `./data:/app` volume으로 연결되므로 이후 Python 코드만 수정했다면 이미지를 매번 다시 build할 필요는 없다. `requirements.txt` 또는 `Dockerfile`이 바뀌었을 때 다시 build한다.

## 2. Azure 로그인

기존 Azure CLI 로그인 volume이 유효하면 건너뛸 수 있다.

```cmd
docker compose --env-file .env.azure --profile data run --rm --no-deps data az account show
```

로그인이 필요하면:

```cmd
docker compose --env-file .env.azure --profile data run --rm --no-deps data az login --use-device-code
```

Shared Key는 사용하지 않는다. `AZURE_STORAGE_ACCOUNT_NAME` + Entra ID/DefaultAzureCredential 경로를 사용한다.

## 3. 실행 준비 점검

Raw/processed/features container 접근과 대상 Raw dataset 존재를 확인한다.

```cmd
run-financial-pipeline.cmd check
```

성공 예시:

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

현재 전체 historical build의 계산은 로컬 Docker `data` 컨테이너 CPU/RAM에서 수행한다. Azure Blob은 source/sink다.

## 5. 단계별 실행

```cmd
run-financial-pipeline.cmd profile
run-financial-pipeline.cmd processed
run-financial-pipeline.cmd features
run-financial-pipeline.cmd audit
```

Profile이 있어야 Processed 계약을 만들 수 있고, 필요한 Processed operation이 있어야 Features를 만들 수 있다.

### Raw Profile

기존 `data/reports/raw-profile/{dataset}.json`이 있으면 기본적으로 재사용한다.

강제로 다시 전수 분석할 때만:

```cmd
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.run_financial_pipeline --stage profile --refresh-profile --schema-version 1 --feature-version 1
```

주의: Raw에 신규 schema/field가 들어왔는데 기존 profile을 계속 재사용하면 Processed 계약에 반영되지 않을 수 있다. 증분 수집 이후 schema drift를 의심하면 profile을 재생성하고 version 정책을 검토한다.

### Processed resume

Processed는 월별 resume를 지원한다. 동일 `schema=v1`에서 Parquet과 quality manifest가 모두 존재하고 manifest의 dataset/operation/year/month/output 계약이 일치하면 해당 월을 건너뛴다.

```text
PROCESSED SKIP dataset=... operation=... year=... month=... rows=...
```

의도적으로 같은 version을 다시 만들 때만:

```cmd
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.run_financial_pipeline --stage processed --schema-version 1 --overwrite
```

### Features 재실행 주의

Features는 Processed와 동일한 월별 resume 계약을 제공한다고 가정하지 않는다. Feature 단계가 실패한 경우 현재 산출물 상태와 version을 먼저 확인하고 재실행한다.

```cmd
run-financial-pipeline.cmd features
```

기존 v1 의미를 바꾸는 코드 변경이라면 같은 v1을 무심코 덮어쓰지 말고 v2 생성 여부를 검토한다.

## 6. 진행률과 ETA

대용량 단계는 진행률과 예상 남은 시간을 출력한다.

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

ETA는 누적 처리량 기반 추정값이며 Azure 네트워크/Parquet 압축/월별 schema 차이로 변동될 수 있다.

## 7. Raw 분석 결과

```text
data/reports/raw-profile/INDEX.md
data/reports/raw-profile/disclosure.{json,md}
data/reports/raw-profile/financial_statement.{json,md}
data/reports/raw-profile/market_index.{json,md}
data/reports/raw-profile/security_product.{json,md}
data/reports/raw-profile/stock_dividend.{json,md}
data/reports/raw-profile/stock_issuance.{json,md}
data/reports/raw-profile/stock_master.{json,md}
data/reports/raw-profile/stock_price.{json,md}
```

JSON은 후속 Processed 타입 계약의 입력이고 Markdown은 사람 검토용이다. 둘 다 역할이 있으므로 JSON을 단순 중복 리포트로 삭제하지 않는다.

## 8. 모델링 산출물

현재 Features v1:

```text
model_stock_daily              training_ready
market_index_daily             training_ready
security_master_latest         reference_only
financial_snapshot             research_only_until_availability_date
financial_company_year_latest  research_only_until_availability_date
```

모델 담당자는 다음 문서를 함께 본다.

```text
data/docs/MODELING_DATASET_CARD.md
data/docs/FEATURE_DICTIONARY.md
data/docs/FINANCIAL_DATA_PIPELINE.md
```

`financial_snapshot`, `financial_company_year_latest`는 OpenDART 실제 공시 availability timestamp가 붙기 전까지 가격 데이터와 자동 JOIN하지 않는다.

또한 현재 `shift(N)` 기반 가격 horizon은 종목별 N번째 관측치를 의미한다. 거래정지가 있는 종목에서는 독립적인 KRX 시장 N거래일 calendar와 다를 수 있다.

## 9. 최종 감사

```cmd
run-financial-pipeline.cmd audit
```

최신 결과:

```text
data/reports/pipeline-runs/latest.json
data/reports/pipeline-runs/latest.md
```

감사 출력에는 Processed/Features 객체 수, metadata record 수, accepted/rejected, conversion error, dataset status, feature manifest, look-ahead 정책이 포함된다.

현재 audit은 운영 현황 집계 성격도 포함하므로, 모든 물리 파일 row count를 독립적으로 다시 스캔하는 완전한 integrity gate와 동일하다고 과장하지 않는다.

## 10. 실패했을 때

우선:

```text
data/reports/pipeline-runs/latest.md
```

를 확인한다.

Processed 실패:

```cmd
run-financial-pipeline.cmd processed
```

완료된 월은 resume 조건을 만족하면 skip된다.

Features 실패:

```cmd
run-financial-pipeline.cmd features
```

재실행 전 기존 Feature version/산출물 상태를 확인한다.

마지막에는:

```cmd
run-financial-pipeline.cmd audit
```

으로 결과를 확인한다.

## 11. Version 정책

현재 최초 전체 build:

```text
Processed schema version = v1
Feature version = v1
```

컬럼/의미/계산 정의가 바뀌어 기존 산출물과 의미적으로 호환되지 않으면 기존 v1을 같은 의미인 것처럼 덮어쓰지 말고 v2를 만든다.
