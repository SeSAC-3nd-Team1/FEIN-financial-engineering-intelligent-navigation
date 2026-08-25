# Financial 8Y Pipeline

## 목적

FE!N의 모델 학습·백테스트용 데이터 기간을 **2018-01-01부터 현재까지**로 통일한다.
사용자는 프로젝트 루트에서 아래 명령 하나만 실행한다.

```cmd
run-financial-8y-pipeline.cmd
```

첫 실행에서는 필요한 전체 과거 구간을 백필하고, 이후 실행에서는 checkpoint와 source별 증분 규칙을 이용해 이미 완료된 구간의 불필요한 재수집을 줄인다.

## 이번 버전의 데이터 범위

### KRX

- KOSPI / KOSDAQ 일별 OHLCV
- 거래량, 거래대금
- 시가총액, 상장주식수
- KOSPI / KOSDAQ / KRX 시장지수

### ECOS

- 한국은행 기준금리
- USD/KRW
- CPI
- 국고채 3년
- 국고채 10년

### OpenDART

- 상장사 corpCode
- KOSPI / KOSDAQ 공시 목록
- 분기·반기·3분기·사업보고 주요 재무계정

## 후속 버전으로 미룬 데이터

- 외국인·기관 수급
- KOSPI200 과거 구성종목 이력
- FRED 및 해외 거시 데이터
- SOX 등 해외 섹터 지수

## 저장 흐름

```text
KRX / ECOS / OpenDART
        ↓
Azure Blob Raw
        ↓
Validation / Normalization
        ↓
Azure Blob Processed Parquet
        ↓
Feature Engineering
        ↓
Azure Blob Features
        ↓
Model / Backtest
```

KRX와 ECOS는 위 파생 흐름까지 자동화한다. OpenDART는 이 버전에서 원문 Raw와 PostgreSQL 정규화 원장을 먼저 구축한다. 재무정보를 가격 Feature와 결합하려면 실제 공시 접수시각을 이용한 Point-in-Time JOIN이 필요하므로, 미래정보 누출을 막기 위해 자동 학습 JOIN은 아직 수행하지 않는다.

## 저장소별 역할

### Azure Blob Raw

외부 API 원문 Source of Truth다. Raw는 수정하거나 삭제하지 않으며 content hash 기반 경로를 사용한다.

### Azure Blob Processed

정규화한 Parquet을 저장한다. KRX 8년 파이프라인은 `schema=v2`를 사용해 기존 v1 산출물을 덮어쓰지 않는다.

### Azure Blob Features

모델이 직접 사용할 시계열 Feature를 저장한다.

- `model_stock_daily/version=v2`
- `market_index_daily/version=v2`
- ECOS macro feature `version=v2`

### PostgreSQL

대규모 학습 Raw를 중복 저장하지 않는다. KRX/OpenDART의 화면 조회 및 서비스용 정규화 데이터만 UPSERT한다.

### Redis

실시간 가격·뉴스·토큰 cache 역할이며 이번 장기 백필 범위에는 포함하지 않는다.

## 실행 순서

`run-financial-8y-pipeline.cmd`는 내부적으로 다음 순서로 실행한다.

1. Alembic migration 적용
2. Azure CLI 로그인 확인
3. KRX 2018-01-01부터 Raw + PostgreSQL 백필
4. KRX Raw → Processed v2 → Features v2 → Coverage Audit
5. ECOS Raw → Processed v2 → Features v2 → Audit
6. OpenDART corpCode → 재무 주요계정 → 공시 백필
7. 실행 state 및 report 저장

## 재실행 / 복구

### KRX

`data/reports/checkpoints/financial-8y-krx.json`에 성공한 날짜를 기록한다. 중간에 종료되면 같은 명령을 다시 실행하고 이미 완료된 날짜는 건너뛴다.

Raw Blob은 content hash 경로를 사용하므로 같은 응답을 다시 저장해도 중복 object를 만들지 않는다.

### ECOS

첫 성공 전에는 2018-01-01부터 전체 구간을 수집한다. 전체 백필 성공 후에는 기존 ECOS incremental 동작을 사용한다.

### OpenDART

상위 state의 마지막 성공 종료일을 기준으로 다음 실행 구간을 줄인다. Raw는 content hash 기반이며 PostgreSQL은 도메인 충돌키로 UPSERT한다.

### 전체 state

```text
data/reports/checkpoints/financial-8y-state.json
```

## 결과 확인

```text
data/reports/pipeline-runs/financial-8y-latest.md
data/reports/pipeline-runs/financial-8y-latest.json
```

KRX Feature coverage audit은 요청 시작일과 실제 첫 거래일 사이의 정상 휴장 차이를 허용하되, 2018년 구간이 통째로 빠진 상태를 성공으로 처리하지 않는다.

## 첫 실행 시 Azure 인증

실행기가 데이터 컨테이너의 Azure CLI 로그인 상태를 확인한다. 로그인 cache가 없다면 같은 명령 실행 중 device login을 요청하고, 성공한 인증은 Compose `azure_cli_data` volume에 유지한다.

API key나 DB 비밀번호를 코드나 문서에 직접 기록하지 않는다. 저장소 루트 `.env`와 Compose 환경변수 계약을 사용한다.
