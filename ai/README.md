# AI Docker 개발환경

모델 개발, 학습, 평가 및 추론 작업을 위한 Python 3.13 개발환경입니다. Host PC의 Python 설치 여부와 관계없이 Docker에서 동일한 의존성을 사용합니다.

## 실행과 접속

명령은 저장소 루트에서 실행합니다. AI profile은 기본 서비스(Frontend, Backend, PostgreSQL, Redis)와 AI 컨테이너를 함께 실행합니다.

```bash
docker compose --profile ai up -d
docker compose exec ai bash
```

컨테이너는 개발 중 계속 Running 상태를 유지합니다. 로컬 `ai/`가 컨테이너 `/app`에 bind mount되므로 코드 변경이 바로 반영됩니다.

## 디렉터리 계약

- `models/`: Ridge, LightGBM 등 모델 정의
- `training/`: 전처리, 시간 분할, Walk-forward 학습
- `evaluation/`: 예측 및 포트폴리오 평가
- `inference/`: 검증된 Artifact 로딩과 종목 점수 산출
- `data_access/`: 버전이 고정된 Azure Feature의 읽기 전용 접근
- `tests/`: 모델·데이터 계약 단위 테스트
- `artifacts/`, `checkpoints/`: 로컬 산출물이며 Git에 포함하지 않음

정식 학습 입력은 PostgreSQL 서빙 테이블이 아니라 Azure `features` 컨테이너의 버전별 Parquet이다.

## Training / Inference 실행

```bash
docker compose exec ai python training/example.py
docker compose exec ai python inference/example.py
docker compose exec ai pytest
docker compose exec ai python --version
```

## VS Code Dev Container

Host Python 없이 VS Code에서 AI Container의 Python 3.13으로 Training, Inference 및 Notebook 코드를 실행할 수 있습니다.

1. Docker Desktop을 실행합니다.
2. VS Code에 Microsoft의 **Dev Containers** Extension을 설치하고 저장소 루트를 엽니다.
3. Command Palette(macOS `Cmd + Shift + P`, Windows `Ctrl + Shift + P`)에서 `Dev Containers: Reopen in Container`를 실행합니다.
4. `SeSAC AI Dev`를 선택합니다. 선택 화면이 없으면 `Dev Containers: Open Folder in Container...`로 저장소 루트를 다시 엽니다.
5. 연결된 터미널에서 다음을 확인합니다.

   ```bash
   python --version
   which python
   ```

   Python 3.13.x와 `/usr/local/bin/python`이 출력되어야 합니다.

6. `training/` 또는 `inference/`의 `.py` 파일은 Microsoft Python Extension의 **Run Python File** 버튼으로 실행합니다. Code Runner의 **Run Code**는 사용하지 않습니다.
7. `.ipynb` 파일은 셀의 Run 버튼으로 실행합니다. 필요하면 `Select Kernel` → `Python Environments`에서 Container Python 3.13을 선택합니다.

VS Code 터미널은 AI Container의 shell이므로 다음처럼 직접 실행할 수도 있습니다.

```bash
python training/example.py
python inference/example.py
python -c "import ipykernel; print(ipykernel.__version__)"
```

Dev Container는 VS Code Window 단위로 연결됩니다. Data도 함께 작업한다면 저장소를 별도 창에서 열고 `SeSAC Data Dev`에 연결합니다.

## Azure Feature 접근

AI 컨테이너는 `DefaultAzureCredential`과 Azure CLI 로그인 캐시를 사용해 Feature를 읽는다. 실제 Azure Shared Key를 소스나 이미지에 넣지 않는다.

최초 한 번 다음 명령으로 로그인한다.

```bash
docker compose --profile ai run --rm ai az login
```

이후 `AZURE_STORAGE_ACCOUNT_NAME`과 선택적인 `AZURE_STORAGE_CONTAINER_FEATURES`를 환경에 설정한다. Compose의 `azure_cli_data` 볼륨이 로그인 캐시를 보존한다.

코드에서는 다음 계약을 사용한다.

```python ai/example_feature_access.py
from data_access import FeatureStore, FeatureStoreConfig

store = FeatureStore(FeatureStoreConfig.from_env())
paths = store.parquet_paths("model_stock_daily", "2")
frame = store.read_partition(paths[0], columns=["stock_code", "trade_date"])
```

### 학습 Dataset 검증과 Manifest

`model_stock_daily`를 학습에 사용하기 전에 전체 버전의 Parquet partition을 검증하고 JSON Manifest를 생성한다.

```bash
docker compose exec ai python training/validate_dataset.py \
  --dataset model_stock_daily \
  --version 2 \
  --output artifacts/model-stock-daily-v2-manifest.json
```

검증은 partition schema 일치, 날짜 범위, 행·종목 수, key 결측·중복, Feature/Target 결측률과 무한대, 120일 warm-up, Target 관측일, split별 eligible target 경계를 확인한다. 오류가 하나라도 있으면 `DatasetValidationError`로 학습 전에 중단하며 Manifest를 쓰지 않는다.

Manifest에는 Dataset/version, schema fingerprint, 기간, 행·종목 수, 결측률, Blob 경로·크기·ETag·수정 시각과 생성 시각이 기록된다. `manifest_id`는 생성 시각을 제외한 Dataset 식별 정보의 SHA-256이므로 같은 입력 파일 집합과 검증 결과는 같은 ID를 갖는다. 각 Blob은 목록 조회 시 얻은 ETag를 조건부 다운로드에 사용하므로 검증 중 파일이 변경되면 읽기가 실패한다.

Azure 접근은 `DefaultAzureCredential` 기반 읽기 전용이며 Shared Key와 원본 Parquet를 저장소에 저장하지 않는다. 출력은 Git에서 제외된 `ai/artifacts/`에 둔다. 현재 구현은 모든 partition을 메모리에 적재하므로 대용량 Dataset 검증 시 컨테이너 메모리를 충분히 확보해야 한다.

## 성과 지표 평가

`evaluation.calculate_performance_metrics`는 일별 수익률 또는 자산 곡선 중 하나를 입력받아 다음 지표를 계산한다.

- 누적 수익률
- 연환산 수익률(CAGR)
- 연환산 변동성
- Sharpe Ratio
- Sortino Ratio
- 최대 낙폭(MDD)
- 승률
- Profit Factor

```python ai/example_performance_evaluation.py
import pandas as pd

from evaluation import calculate_performance_metrics

metrics = calculate_performance_metrics(
    daily_returns=pd.Series([0.01, -0.02, 0.015]),
    periods_per_year=252,
    annual_risk_free_rate=0.0,
)
print(metrics.to_dict())
```

입력과 결과의 수익률 단위는 퍼센트가 아닌 소수 비율이다. 예를 들어 1%는 `0.01`로 전달한다. `daily_returns`와 `equity_curve`는 동시에 전달할 수 없으며, 날짜 index는 중복 없이 오름차순이어야 한다. CAGR은 관측 구간 수를 연환산 기준으로 나눠 계산하고, 변동성과 Sharpe Ratio는 표본 표준편차를 사용한다. Sortino Ratio는 0 미만 초과수익률의 하방 편차를 사용한다.

0 변동성, 하락 관측 없음, 손실 없음처럼 비율의 분모가 0인 경우 JSON 비호환 무한대 대신 `None`을 반환한다. NaN, 무한대, `-100%` 이하의 일별 수익률, 0 이하의 자산 값은 명시적으로 거부한다.

## 가격 기반 추천 Snapshot MVP

`inference.recommendation_snapshot.build_recommendation_snapshot`은 최신 거래일의 `is_tradable` 및
`risk_eligible` 종목만 대상으로 120일 모멘텀 순위를 계산하고 목표 비중을 생성한다. 결과 계약은
`as_of`, 모델·데이터 버전, 시장 국면과 종목별 점수·순위·목표 비중·선정 사유를 포함한다.

실제 E2E 실행 경로인 `inference.generate_latest_recommendations` CLI는 Azure의
`model_stock_daily`에서 모델 Feature를, `algorithm_ohlcv`에서 거래 가능 여부를 읽어 자연키로
결합하고 AI Risk Filter를 적용한다. 이어 실제 모델 함수를 실행한 뒤 JSON을 임시 파일에 먼저 쓰고
원자적으로 교체한다. Compose에서는 AI의
`/model-artifacts/model_recommendation_snapshot.json`과 Backend의 동일 경로가 전용 볼륨으로 연결된다.

```bash
docker compose --profile ai run --rm ai python -m inference.generate_latest_recommendations \
  --model-version 2 \
  --algorithm-version 2 \
  --top-n 5
```

두 Dataset의 최신 거래일이나 자연키가 어긋나면 오래되거나 불완전한 추천을 발행하지 않고 실패한다.
`data_version`에는 `model_stock_daily`, `algorithm_ohlcv`, Risk Filter 버전이 모두 기록된다.
생성 결과는 Backend의
`GET /api/v1/model-recommendations/latest`에서 계약 검증 후 제공된다. 로컬 E2E 경로는 고정 Feature
fixture로 다음과 같이 재현할 수 있다.

이미 결합된 CSV/Parquet로 재현하거나 디버깅할 때는 기존
`inference.export_recommendation_snapshot` CLI를 사용할 수 있으며, 이 입력에는 `trade_date`,
`stock_code`, `market_cap`, `momentum_120d`, `is_tradable`, `risk_eligible`이 필요하다.

```bash
./scripts/verify_model_recommendation_e2e.sh
```

공유 artifact가 아직 없거나 손상된 경우 Backend는 시연 안정성을 위해 동일 generator 제약(주식 95%,
현금 5%)에 맞춘 `backend/app/data/model_recommendation_snapshot.json`을 fallback으로 읽는다. 운영에서는
`MODEL_RECOMMENDATION_SNAPSHOT_PATH`로 artifact 위치를 바꿀 수 있다. 이 MVP는 가격 데이터 기반
가상투자 참고용이며 수급·재무 Feature, 성능 보장, 실제 주문은 범위에 포함하지 않는다.

## Dependency 추가

`ai/requirements.txt`에 필요한 패키지와 버전을 추가한 뒤 이미지를 다시 빌드합니다.

```bash
docker compose build ai
docker compose --profile ai up -d
```

PyTorch와 TensorFlow 같은 대용량 패키지는 초기 환경에 포함하지 않습니다. 실제 모델, CPU/GPU 실행 방식 및 호환 버전이 확정된 뒤 추가합니다.

Dev Container를 사용 중이면 `ai/requirements.txt` 수정 후 Command Palette의 `Dev Containers: Rebuild Container`로 이미지를 다시 빌드합니다. VS Code Notebook 실행에는 `ipykernel`을 사용하며, 브라우저 기반 JupyterLab은 포함하지 않습니다.

기존 CLI 방식도 그대로 지원합니다.

```bash
docker compose --profile ai up -d
docker compose exec ai python training/example.py
docker compose exec ai python inference/example.py
```

## PostgreSQL / Redis 접근

Compose 네트워크에서는 `localhost` 대신 서비스명을 사용합니다. 연결 문자열은 `.env` 또는 `.env.example` 형식을 따르며 컨테이너에 `DATABASE_URL`, `REDIS_URL`로 전달됩니다.

- PostgreSQL: `postgres:5432`
- Redis: `redis:6379`

실제 Secret은 이미지, 소스 코드 또는 Compose 파일에 기록하지 않습니다.

## 상태 확인과 종료

```bash
docker compose ps
docker compose logs -f ai
docker compose down
```

`docker compose down`은 컨테이너를 제거하지만 PostgreSQL과 Redis의 named volume 데이터는 유지합니다.
