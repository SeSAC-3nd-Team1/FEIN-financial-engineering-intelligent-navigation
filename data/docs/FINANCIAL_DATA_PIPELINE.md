# 금융 데이터 파이프라인 v1

## 구조

```text
공공데이터 API
      ↓
Azure Blob raw
JSONL.GZ envelope
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
Modeling
```

한투 API는 이 파이프라인 범위에 포함하지 않는다. 서비스 단계의 실시간/최신 시세 공급원으로 별도 연결한다.

## Raw

Canonical path:

```text
raw/data-go-kr/{dataset}/operation={operation}/year=YYYY/month=MM/{sha256}.jsonl.gz
```

JSONL 한 줄 구조:

```json
{
  "collectedAt": "...",
  "dataset": "stock_price",
  "legacy": {},
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

`payload`만 business data이며 나머지는 lineage다.

## Raw Profile

프로파일러는 전체 데이터를 한 번에 메모리에 올리지 않고 Blob 단위로 읽는다.

기록 항목:

- dataset / operation별 Blob 수와 row 수
- `basDt` 범위와 월별 row 분포
- field 목록
- present / missing / null / empty
- 숫자 변환 가능률
- 정수 변환 가능률
- YYYYMMDD 변환 가능률
- cardinality(상한 적용)
- 문자열 길이
- 숫자 min/max
- 예시값
- malformed JSON / invalid payload

2026-08-16 전수 프로파일 기준 8 datasets / 52 operations / 24,073,651 rows에서 malformed JSON과 invalid/missing `payload.basDt`는 0건이었다.

## Processed

Path:

```text
processed/{dataset}/operation={operation}/schema=v1/year=YYYY/month=MM/part-00000.parquet
```

Quality manifest:

```text
processed/_quality/{dataset}/operation={operation}/schema=v1/year=YYYY/month=MM/manifest.json
```

Manifest에는 다음을 남긴다.

- 원본 source blob 목록
- accepted / rejected row 수
- reject reason
- field conversion error
- output bytes/path
- 생성 시각
- Git SHA
- `raw_immutable=true`

### 타입 규칙

- `YYYYMMDD` 100% 유효 → `date`
- 정수 100%이며 int64 범위 내 → `int64`
- 숫자 100%이며 float64 범위 내 → `float64`
- 그 외 → `string`
- 종목코드/법인번호/ISIN/각종 코드/ID → 무조건 `string`
- 빈 문자열 → NULL
- 범위를 초과하는 숫자형 문자열 → 원문 `string` 보존

### Core operation 표준 이름

핵심 모델링 source는 사람이 이해하기 쉬운 표준 컬럼명으로 변환한다.

예:

```text
basDt     → trade_date
srtnCd    → stock_code
clpr      → close_price
trqu      → volume
mrktTotAmt → market_cap
```

비핵심 operation도 데이터를 버리지 않고 camelCase를 snake_case로 바꿔 operation별 Processed Parquet에 보존한다.

## Features

Path:

```text
features/{dataset}/version=v1/year=YYYY/month=MM/part-00000.parquet
```

전체 manifest:

```text
features/_manifests/model-datasets/version=v1/manifest.json
```

생성 Dataset:

- `model_stock_daily`: 학습 가능
- `market_index_daily`: 학습 가능
- `security_master_latest`: reference only
- `financial_snapshot`: availability date 해결 전 research only
- `financial_company_year_latest`: availability date 해결 전 research only

## Look-ahead / Survivorship 방지

### 가격 Target

Feature는 현재 및 과거 데이터만 사용한다. 미래 수익률은 `target_*`로 분리하고 입력 X에 넣지 않는다.

시간순 70/15/15 split을 만들며 Target의 미래 날짜가 split 경계를 넘는 행은 `eligible_target_* = false`로 표시한다.

### 재무 데이터

회계 `base_date`를 실제 정보 공개일로 간주하지 않는다. OpenDART 접수일 등 실제 public availability timestamp를 확보하기 전에는 가격과 point-in-time JOIN하지 않는다.

### 종목 기준정보

`security_master_latest`는 표시/매핑용이다. 현재 살아 있는 종목만 이용해 과거 Universe를 만들지 않는다.

## 실행

### 전체 Raw 프로파일

```cmd
python scripts/profile_raw_data.py --dataset stock_price --output-dir reports/raw-profile
```

8개 dataset 각각 실행한다. 대용량이므로 CI에서는 dataset matrix 병렬 실행을 권장한다.

### 전체 Processed + Features

```cmd
python scripts/run_financial_pipeline.py --profile-dir reports/raw-profile --schema-version 1 --feature-version 1
```

특정 dataset의 Processed만 재생성:

```cmd
python scripts/run_financial_pipeline.py --dataset stock_price --skip-features --profile-dir reports/raw-profile --schema-version 1 --overwrite
```

Features만 재생성:

```cmd
python scripts/run_financial_pipeline.py --skip-processed --schema-version 1 --feature-version 1 --overwrite
```

### Docker + Azure 환경

프로젝트 루트 기준:

```cmd
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.run_financial_pipeline --profile-dir reports/raw-profile --schema-version 1 --feature-version 1
```

Raw profile JSON이 컨테이너 내부 `data/reports/raw-profile`에 있어야 한다.

### 산출물 감사

```cmd
python scripts/audit_model_data_outputs.py --schema-version 1 --feature-version 1 --output reports/financial-pipeline-output-audit.json
```

Processed/Features의 Parquet 객체 수, metadata record count, bytes, quality rejection/conversion error, 최종 manifest를 확인한다.

## 증분 운영 방향

v1은 전체 historical build를 위한 구조다. 이후 정기 운영은 다음처럼 바꾼다.

```text
새 Raw month 수집
→ 해당 dataset/operation/month만 Processed 재생성
→ 영향을 받는 Feature 최근 lookback 구간만 재계산
→ manifest/version 갱신
```

120일 모멘텀/60일 변동성 등이 있으므로 Feature 증분 계산 시 현재 월만 읽지 않고 충분한 lookback 기간을 함께 읽어야 한다.
