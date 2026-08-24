# 금융 데이터 파이프라인 v1

## 구조

```text
공공데이터 API
      ↓
Azure Blob raw
JSONL.gz envelope
      ↓
Raw Profile
field/type/null/cardinality/range/distribution
      ↓
Validation + Normalization
      ↓
Azure Blob processed
operation별 월별 Parquet + quality manifest
      ↓
Feature Engineering
      ↓
Azure Blob features
모델용 Parquet + dataset manifest
      ↓
Modeling / Backtest
```

KIS는 이 오프라인 학습 파이프라인 범위에 포함하지 않는다. 서비스 단계의 실시간/최신 시세 및 모의투자 경로로 별도 연결한다.

## Raw

Canonical path:

```text
raw/data-go-kr/{dataset}/operation={operation}/year=YYYY/month=MM/{sha256}.jsonl.gz
```

신규 collector가 저장하는 JSONL 한 줄:

```json
{
  "collectedAt": "...",
  "dataset": "stock_price",
  "operation": "getStockPriceInfo",
  "payload": {
    "basDt": "20260813",
    "srtnCd": "005930",
    "clpr": "..."
  },
  "payloadHash": "...",
  "source": "data-go-kr"
}
```

`payload`가 business data이며 나머지는 lineage다. 과거 SQL→Blob migration 과정에서 만들어진 일부 envelope에는 복원용 `legacy` metadata가 존재할 수 있지만 신규 collector는 이를 추가하지 않는다.

Raw payload는 수정하지 않는다. `payload.basDt`를 canonical 월 partition/filter의 권위 있는 날짜로 사용한다.

## Raw Profile

프로파일러는 전체 데이터를 한 번에 메모리에 올리지 않고 Blob 단위로 읽는다.

기록 항목:

- dataset / operation별 Blob 수와 row 수
- `basDt` 범위와 월별 row 분포
- field 목록
- present / missing / null / empty
- 숫자/정수/YYYYMMDD 변환 가능률
- cardinality 상한
- 문자열 길이
- 숫자 min/max
- 예시값
- malformed JSON / invalid payload

2026-08-16 전수 프로파일 기준 8 datasets / 52 operations / 4,228 blobs / 24,073,651 rows에서 malformed JSON과 invalid/missing `payload.basDt`는 0건이었다.

```text
data/reports/raw-profile/INDEX.md
data/reports/raw-profile/{dataset}.json
data/reports/raw-profile/{dataset}.md
```

JSON은 Processed 타입 계약 입력으로 실제 코드가 읽고, Markdown은 사람이 검토한다.

## Processed

Path:

```text
processed/{dataset}/operation={operation}/schema=v1/year=YYYY/month=MM/part-00000.parquet
```

Quality manifest:

```text
processed/_quality/{dataset}/operation={operation}/schema=v1/year=YYYY/month=MM/manifest.json
```

Manifest에는 source blob 목록, accepted/rejected, reject reason, conversion error, output bytes/path, 생성 시각, Git SHA, `raw_immutable=true`를 기록한다.

### 타입 규칙

- `YYYYMMDD` 100% 유효 → `date`
- 정수 100%이며 int64 범위 내 → `int64`
- 숫자 100%이며 float64 범위 내 → `float64`
- 그 외 → `string`
- 종목코드/법인번호/ISIN/코드/ID → 문자열 보존
- 빈 문자열 → NULL
- 범위를 초과하는 숫자형 문자열 → 원문 string 보존

평균/중앙값 대체, 일괄 0 대체, StandardScaler/MinMaxScaler 같은 모델 종속 전처리는 이 단계의 기본 책임이 아니다.

### Core operation 표준 이름

예:

```text
basDt      → trade_date
srtnCd     → stock_code
clpr       → close_price
trqu       → volume
mrktTotAmt → market_cap
```

비핵심 operation도 데이터를 버리지 않고 camelCase를 snake_case로 바꿔 operation별 Processed Parquet에 보존한다.

### Resume

동일 schema version에서 월별 Parquet과 quality manifest가 모두 존재하고 manifest 계약이 일치하면 해당 월을 다시 읽지 않는다.

```text
PROCESSED SKIP dataset=... operation=... year=... month=... rows=...
```

`--overwrite`는 의도적 재생성에만 사용한다.

## Features

Path:

```text
features/{dataset}/version=v1/year=YYYY/month=MM/part-00000.parquet
```

전체 manifest:

```text
features/_manifests/model-datasets/version=v1/manifest.json
```

현재 생성 Dataset:

- `model_stock_daily`: training ready
- `market_index_daily`: training ready
- `security_master_latest`: reference only
- `financial_snapshot`: availability date 해결 전 research only
- `financial_company_year_latest`: availability date 해결 전 research only

가격 Feature에는 1개 관측치 수익률, 5/20/60/120개 관측치 momentum, 5/20/60개 관측치 이동평균, 20/60개 관측치 변동성, 거래량 평균/비율 등이 포함된다. 미래 5/20번째 관측치 수익률은 `target_*`으로 분리한다.

### Horizon 의미 주의

현재 구현은 종목별 DataFrame에서 `shift(N)`/`rolling(N)`을 사용한다. 따라서 `N`은 해당 종목의 N번째 관측치를 의미한다.

거래가 매일 존재하는 일반 종목에서는 대체로 N거래일과 같지만, 거래정지/관측 누락이 있으면 독립적인 KRX 시장 N거래일 calendar와 다를 수 있다. 문서에서 이를 무조건 '시장 N거래일'이라고 해석하지 않는다.

## Look-ahead / Survivorship 방지

### 가격 Target

미래 수익률은 `target_*`로 분리하며 입력 X에 넣지 않는다. 시간순 70/15/15 split을 만들고 Target 날짜가 split 경계를 넘는 행은 `eligible_target_* = false`로 표시한다.

### 재무 데이터

회계 `base_date`를 실제 공개일로 간주하지 않는다. OpenDART 접수일 등 실제 public availability timestamp를 확보하기 전에는 가격과 point-in-time JOIN하지 않는다.

### 종목 기준정보

`security_master_latest`는 표시/매핑용이다. 최신 종목 목록만 이용해 과거 Universe를 재구성하지 않는다.

### 수정주가

현재 가격 Feature는 원천 `close_price` 기반이다. 액면분할/권리락 등 corporate action을 완전히 반영한 수정주가 계열이 별도 보강되기 전에는 장기 수익률/백테스트 해석에 주의한다.

## 실행 CLI

Windows CMD, 프로젝트 루트:

```cmd
run-financial-pipeline.cmd check
run-financial-pipeline.cmd profile
run-financial-pipeline.cmd processed
run-financial-pipeline.cmd features
run-financial-pipeline.cmd audit
run-financial-pipeline.cmd all
```

직접 Python CLI:

```cmd
docker compose --profile data run --rm --no-deps data python -m scripts.run_financial_pipeline --stage all --schema-version 1 --feature-version 1
```

Raw profile 강제 재생성:

```cmd
docker compose --profile data run --rm --no-deps data python -m scripts.run_financial_pipeline --stage profile --refresh-profile --schema-version 1 --feature-version 1
```

Processed 강제 재생성:

```cmd
docker compose --profile data run --rm --no-deps data python -m scripts.run_financial_pipeline --stage processed --schema-version 1 --overwrite
```

## 실행/감사 기록

```text
data/reports/pipeline-runs/latest.json
data/reports/pipeline-runs/latest.md
```

Audit은 Processed/Features 객체 수, metadata record count, quality manifest, status 등을 집계한다. 현재 구현을 모든 Parquet row를 독립적으로 재스캔하는 완전한 integrity gate로 과장하지 않는다.

## 증분 운영 방향

```text
새 Raw month 수집
→ 영향 operation/month Processed 재생성
→ 충분한 lookback을 포함해 Feature 재계산
→ manifest/version 갱신
```

120개 관측치 momentum/60개 관측치 변동성 등이 있으므로 Feature 증분 계산은 현재 월만 읽어서는 안 된다.
## ECOS 거시경제 파이프라인

ECOS는 `Raw → Processed(schema=v1) → macro_daily(version=v1)` 순서로 처리한다.

- Raw: provider 행을 손실 없이 월별 JSONL.gz로 저장한다.
- Processed: `ecos/operation={series}/schema=v1/year=YYYY/month=MM/part-00000.parquet`에
  숫자·날짜·단위·lineage를 정규화한다. 동일 자연키의 값 충돌은 실패 처리한다.
- Features: 환율과 국고채 실제 관측일의 합집합을 거래일 축으로 삼아
  `macro_daily/version=v1/year=YYYY/month=MM/part-00000.parquet`에 저장한다.
- 품질: 시계열별 source/accepted/rejected/duplicate/null/날짜 범위와 source blob을
  `processed/_quality/ecos/.../manifest.json`에 기록한다.

ECOS `StatisticSearch`에는 CPI 공표 timestamp가 없으므로 관측월의 두 번째 다음 달 1일을
보수적 `available_at`으로 사용한다. 모든 as-of 결합은 `available_at <= feature date`만
허용한다. 따라서 최신성은 실제 공표일보다 늦을 수 있지만 미래 정보 유입은 줄어든다.
