# Azure Blob Raw EDA

Azure Blob Storage의 canonical Raw 데이터를 Docker `data` 컨테이너에서 분석하는 방법을 정리한다.

## 분석 범위

`data/scripts/analyze_blob_data.py`는 기존 `scripts.profile_raw_data` 결과를 dataset 수준으로 요약한다.

- dataset / operation / Blob / record 규모
- `basDt` 최소·최대 범위
- history / snapshot / mixed 시간축 분류
- malformed JSON, invalid payload, `basDt` 누락·오류 합계
- 결측률이 높은 필드와 완전 빈 필드 수
- dataset 내부에서 가장 큰 operation 및 record 비중
- dataset별 압축 저장량과 record 밀도

결측률이 높다고 필드를 자동 삭제하지 않는다. 공시·배당·발행정보처럼 operation마다 의미가 다른 데이터는 필드 의미를 확인한 뒤 전처리 정책을 결정한다.

## 기존 프로파일 기준 EDA

프로젝트에 커밋된 `reports/raw-profile/*.json`을 사용하므로 Azure 인증 없이도 동일한 EDA 요약을 재현할 수 있다.

```bash
docker compose --profile data run --rm --no-deps data \
  python -m scripts.analyze_blob_data
```

특정 dataset만 분석하려면 `--dataset`을 반복해서 지정한다.

```bash
docker compose --profile data run --rm --no-deps data \
  python -m scripts.analyze_blob_data \
  --dataset stock_price \
  --dataset market_index
```

## Azure Blob 최신 데이터 재분석

실제 Azure Storage는 프로젝트 보안 정책에 따라 Shared Key가 아니라 `DefaultAzureCredential`을 사용한다. Docker Compose의 `azure_cli_data` volume에 Azure CLI 로그인 캐시를 유지한다.

Docker 환경에서 Azure CLI 로그인이 아직 없다면 한 번 로그인한다.

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  az login --use-device-code
```

현재 Blob을 직접 다시 읽어 전체 dataset을 프로파일링하고 EDA를 생성한다.

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.analyze_blob_data --refresh-profile
```

대용량 dataset 전체 재분석 전에 특정 dataset만 확인할 수 있다.

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.analyze_blob_data \
  --refresh-profile \
  --dataset stock_price
```

## 결과 위치

분석 결과는 Git에 커밋하지 않는 `data/exports/` 아래에 생성한다.

```text
data/exports/blob-eda/
├─ summary.json
├─ summary.md
└─ profiles/          # --refresh-profile 사용 시 최신 profile cache
   ├─ {dataset}.json
   └─ {dataset}.md
```

Raw 원본은 읽기만 하며 수정하지 않는다. Live profile 결과도 Raw/Processed/Features 컨테이너에 자동 업로드하지 않는다.

## 시간축 해석

- `history`: operation의 `basDt`가 여러 날짜에 걸쳐 존재한다.
- `snapshot`: operation의 `basDt`가 한 날짜에만 존재한다.
- `mixed`: 같은 dataset 안에 history와 snapshot operation이 함께 존재한다.

`mixed` dataset은 하나의 공통 시간축 테이블로 바로 합치지 않고 operation별 의미를 분리한 뒤 Processed 계약을 정의한다.

## 테스트

```bash
docker compose --profile data run --rm --no-deps data \
  python -m pytest tests -q
```
