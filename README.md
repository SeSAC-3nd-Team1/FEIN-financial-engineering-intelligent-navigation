# SeSAC 3차 프로젝트 1팀

Docker Compose 기반의 공통 개발환경입니다. 일반 개발·시연용 서비스 DB는 팀 공용 **Azure Database for PostgreSQL Flexible Server 1개**만 사용합니다. 로컬 PostgreSQL fallback은 제공하지 않습니다.

## Development setup

### 1. 준비

1. Git과 Docker Desktop을 설치합니다.
2. Docker Desktop을 실행하고 엔진이 준비될 때까지 기다립니다.
3. 저장소를 복제하고 `develop` 브랜치로 이동합니다.

```bash
git clone https://github.com/SeSAC-3nd-Team1/SeSAC-3nd-Team1-project.git
cd SeSAC-3nd-Team1-project
git switch develop
```

Windows에서는 PowerShell/CMD, macOS에서는 Terminal을 사용할 수 있습니다. WSL2는 필수가 아닙니다.

### 2. 환경 변수

예제 파일을 복사해 로컬 전용 `.env`를 만듭니다.

```bash
cp .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

외부 API를 사용하는 작업이라면 `.env`의 빈 Secret 항목을 채웁니다. 로컬 환경 파일은 루트 `.env` 하나만 사용하며, 과거의 `.env.azure` 같은 서비스별 환경 파일은 사용하지 않습니다. `.env`와 `.env.*`는 Git에서 제외되며 실제 키를 소스, Dockerfile, Compose 파일, 문서에 기록하면 안 됩니다. 변수별 설정 위치와 관리 원칙은 [환경 변수 관리 가이드](docs/ENVIRONMENT_VARIABLES.md)를 따릅니다.

PostgreSQL은 `.env`의 `DATABASE_URL`에 팀 공용 Azure Database for PostgreSQL URL을 반드시 설정합니다. 공공데이터 수집 시 사용하는 `DATA_GO_KR_API_KEY`를 포함한 외부 API 키도 같은 `.env`에 설정합니다. `DATABASE_URL`에는 `?sslmode=require`를 포함하며 실제 Azure 사용자명·비밀번호·호스트는 GitHub에 올리지 않습니다. `DATABASE_URL`이 없거나 빈 값이면 Docker Compose는 실행을 중단합니다. 전체 준비 절차와 Portal/CLI 작업은 [Azure PostgreSQL 단일 프로젝트 DB 가이드](docs/AZURE_POSTGRESQL_DEV.md)를 따릅니다.

공용 환경에서는 `JWT_SECRET`을 긴 무작위 값으로 설정하고 팀 Backend가 동일한 값을 사용합니다. KIS는 `KIS_APP_KEY`/`KIS_APP_SECRET`으로 **현재가만 조회**하며 KIS 주문 API는 사용하지 않습니다. OAuth token은 Redis에서 만료시간과 함께 공유해 요청별 재발급을 방지합니다. 신규 가상계좌는 운용방식별 0원 계좌로 생성되고 투자 온보딩 입금 API에서 현재 부족분만 정확히 한 번 충전합니다.

한국 금융 뉴스는 NAVER Cloud Platform의 NAVER API HUB Search News API를 Backend에서만 호출합니다. 로컬 `.env`에 `NAVER_API_HUB_CLIENT_ID`와 `NAVER_API_HUB_CLIENT_SECRET`을 설정하고 실제 값은 커밋하거나 로그에 출력하지 않습니다. 기본 검색어는 `NEWS_SEARCH_QUERY=증시`, Redis cache TTL은 `NEWS_CACHE_TTL_SECONDS=300`입니다.

Azure Blob을 사용하는 Data 작업은 Azure CLI/Entra ID 인증을 사용합니다. Shared Key 기반 실제 Azure connection string은 사용하지 않습니다.

### 3. 기본 개발환경 실행

```bash
docker compose up -d
```

최초 실행이거나 Dockerfile 및 dependency가 변경되었다면 `docker compose up -d --build`를 사용합니다. 기본 실행에는 Frontend, Backend, Redis만 포함되며 로컬 PostgreSQL 컨테이너와 migration job은 생성하지 않습니다. Data, AI, migration 작업은 profile로 분리됩니다.

DB schema 변경 담당자는 migration을 임시/CI PostgreSQL에서 먼저 검증하고 `develop` 반영 후에만 공용 Azure DB에 적용합니다.

```bash
git switch develop
git pull origin develop
docker compose --profile migration run --rm --no-deps db-init
```

`db-init`은 Alembic migration과 약관 seed를 명시적으로 실행합니다. 동일한 `SIGNUP_TERMS_VERSION`으로 반복해도 `(term_code, version)` UNIQUE와 `ON CONFLICT DO NOTHING` 때문에 중복 약관이 생기지 않습니다. feature branch에서 공용 Azure DB에 실행하면 아직 merge되지 않은 schema가 먼저 적용될 수 있으므로 금지합니다.

실행 후 dependency 상태를 확인합니다.

```bash
docker compose ps
curl --fail http://localhost:8000/health/dependencies
```

정상 결과는 `{"postgres":"ok","redis":"ok"}`입니다.

Backend가 실제 Azure DB를 보고 있는지 비밀번호 노출 없이 확인할 수 있습니다.

```bash
docker compose exec backend python -c "from app.core.config import settings; from urllib.parse import urlsplit; u=urlsplit(settings.database_url); print('DB HOST =', u.hostname); print('DB =', u.path.lstrip('/'))"
```

`DB HOST = postgres`가 아니라 `<server>.postgres.database.azure.com` 형태여야 합니다.

Backend 테스트:

```bash
docker compose run --rm --no-deps backend pytest -q
```

공용 Azure PostgreSQL/Redis E2E 테스트:

```bash
docker compose --profile migration run --rm --no-deps db-init
docker compose exec -T backend env RUN_INTEGRATION=1 pytest -q tests/test_integration_flow.py
```

E2E는 `GET /auth/terms`부터 회원가입 동의 저장, AUTO/SEMI_AUTO별 계좌, 부족분 가상 입금과
멱등 재시도, 전략·매수·매도·원장 정합성까지 확인합니다. 체결 이후에는 포트폴리오 홈의
평가·자산 배분·기간별 snapshot 추이, 거래내역 cursor 페이지 이동과 잘못된 cursor, 다른
사용자의 계좌 접근 차단도 실제 PostgreSQL/Redis 데이터로 검증합니다. 생성한 사용자와
가상거래 관계 및 전용 Redis 가격 key만 테스트 종료 시 FK 역순으로 제거하며 공용 개발 데이터
전체를 삭제하지 않습니다. 전체 schema drop/recreate, 전체 truncate, migration rollback 같은
파괴적 테스트는 별도 임시 PostgreSQL에서만 수행합니다.

### 개발 전용 Mock/데모 정책

Mock 백테스트와 데모 포트폴리오는 개발·시연 환경에서만 사용할 수 있습니다. 운영 빌드는 `VITE_USE_MOCK_BACKTEST=true` 설정을 감지하면 실패하며, Mock 백테스트를 사용하는 개발 화면에는 `DEMO` 배지가 표시됩니다. 실제 API 오류가 Mock 결과로 대체되지는 않습니다.

`seed_demo_portfolio`와 `seed_demo_account`는 모두 `DEMO_SEED_ENABLED=true`가 명시되고 `APP_ENV`가 `development`, `dev`, `local`, `test`, `demo` 중 하나일 때만 실행할 수 있습니다. `APP_ENV`가 없거나 알 수 없는 값이면 실행을 거부합니다. 운영 환경에서 데모 계정·주문을 생성하지 마세요.

기존 Frontend Mock의 20개 종목·비중을 특정 개발용 가상계좌에 PostgreSQL 최신 KRX 종가
기준의 실제 가상 주문으로 한 번만
적용하려면 다음 명령을 사용합니다. 소수점 8자리 수량으로 각 Mock 목표 비중을 맞추고,
전체 비용이 계좌 현금 이내인지 주문 전에 검증합니다.
먼저 `--dry-run`으로 수량을 확인할 수 있으며, 종목별 고정
idempotency key를 사용하므로 중간 실패 후 같은 명령을 다시 실행해도 완료된 주문은 중복되지
않습니다. 비밀번호나 이메일 대신 로그인 아이디만 인자로 전달합니다.

```bash
docker compose run --rm backend python -m scripts.seed_demo_portfolio --user-id <개발용-로그인-id> --dry-run
docker compose run --rm backend python -m scripts.seed_demo_portfolio --user-id <개발용-로그인-id>
```

포트폴리오의 `1M / 3M / 1Y` 수익률 화면을 바로 시연할 수 있는 가상 계정은 다음 명령으로
생성합니다. 성장추구형 사용자가 `momentum` 전략으로 자동투자를 시작한 시나리오이며, DB에
저장된 최근 253개 거래일의 종목 종가와 KOSPI 데이터를 사용해 매월 당시 시점에 이용할 수
있던 데이터만으로 `price-momentum-v1` 규칙을 다시 실행하고, 그 월의 모델 종목과 목표
비중으로 리밸런싱합니다. 최신 시점의 재현 결과가 실제 `generated` 산출물과 일치하지 않으면
시드를 중단하며 종목을 임의로 추가하거나 제외하지 않습니다.
주문·체결·현금 원장·최종 포지션·일별 스냅샷은 하나의 transaction으로 저장합니다. 같은
명령을 다시 실행하면 기존 데모 계정을 반환하며 중복 거래를 생성하지 않습니다.

운영 환경에서는 실행할 수 없고, 실수로 실행하는 것을 막기 위해 `DEMO_SEED_ENABLED=true`를
매번 명시해야 합니다. 비밀번호는 파일에 저장하지 말고 실행 환경 변수로만 전달합니다.

```bash
docker compose run --rm \
  -e DEMO_SEED_ENABLED=true \
  -e DEMO_ACCOUNT_PASSWORD='<데모-비밀번호>' \
  backend python -m scripts.seed_demo_account
```

기본 로그인 아이디는 `demomin32`이며 이름·생년월일·전화번호·이메일은 실사용자와 구분되는
가상 값입니다. 기존 사용자와 아이디가 충돌하면 덮어쓰지 않고 실패합니다. 다른 아이디와
이메일이 필요하면 `--user-id`와 `--email`을 함께 지정합니다.

실제 KIS 시세→Redis 통합 테스트는 유효한 KIS 환경 변수가 있는 경우에만 명시적으로 실행합니다. 이 테스트는 현재가 조회만 수행하고 KIS 주문 API나 실제·모의 계좌 주문을 호출하지 않습니다.

```bash
docker compose exec -T backend env RUN_KIS_INTEGRATION=1 pytest -q tests/test_kis_integration.py
docker compose exec -T redis redis-cli --scan --pattern "price:*"
docker compose exec -T redis redis-cli TTL price:005930
```

실제 NAVER 뉴스→Redis 통합 테스트도 credential이 있는 로컬에서만 명시적으로 실행합니다.

```bash
docker compose exec -T backend env RUN_NAVER_NEWS_INTEGRATION=1 pytest -q tests/test_naver_news_integration.py
docker compose exec -T redis redis-cli --scan --pattern "information:news:kr:*"
docker compose exec -T redis redis-cli TTL "information:news:kr:증시:1:20"
```

뉴스 API는 `GET /api/v1/information/news/kr?page=1&size=20`이다. NAVER 검색 결과만 정규화하며 뉴스 본문을 scraping하지 않는다. 뉴스는 PostgreSQL이나 Azure Blob에 저장하지 않고 Redis에만 단기 cache한다. Information 화면의 새로고침은 Backend를 다시 호출하지만 TTL 동안은 Redis 응답을 사용한다.

Frontend 로그인은 `/api/v1/auth/login`과 `/api/v1/auth/me`를 사용한다. JWT는 브라우저에 보관되어 새로고침 후 검증·복원되며, 로그아웃 시 제거된다.

투자성향 분석은 인증된 `POST /api/v1/investor-profile/analyze` 요청으로 처리한다. Backend는 `v1` 설문의 8개 문항 ID와 선택지 ID를 검증한 뒤 `risk-score-v1` 고정 점수표와 보수적 제한 규칙으로 0~100점 및 5단계 투자유형을 계산한다. 원본 답변은 저장하지 않고 점수·분류 결과·재현 버전만 PostgreSQL에 저장하며, Azure OpenAI 설정 없이 같은 HTTP 요청에서 결과를 반환한다.

Frontend 가상투자 화면은 FastAPI만 호출한다. `/auth/me`의 `active_operation_mode`를 복원하고
`/accounts/me?operation_mode=`로 AUTO/SEMI_AUTO별 동적 계좌 ID를 얻은 뒤 `/portfolio` 한 번으로
현금·보유종목·현재 평가를 조회한다. 운용방식 전환은 완료된 별도 계좌 사이에서
`PUT /accounts/me/active-operation-mode`를 사용하며 계좌 자산이나 거래 이력을 이동하지 않는다.
시장가 BUY/SELL은 UUID idempotency key와 함께 `/orders`로 보내며 성공 후
portfolio/orders/executions를 다시 조회한다. KIS는 Backend `MarketService`의 가격 공급자로만
사용하고, 가상계좌·가상 입금·주문·체결·포지션·현금원장은 Azure PostgreSQL에서 관리한다.
브라우저 bundle에는 KIS key/secret이나 KIS 직접 호출 URL이 포함되지 않는다.

| 서비스 | 접속/확인 위치 |
| --- | --- |
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 |
| Backend health | http://localhost:8000/health |
| Dependency health | http://localhost:8000/health/dependencies |
| Swagger UI | http://localhost:8000/docs |
| PostgreSQL | `.env`의 Azure PostgreSQL 원격 host |
| Redis | `localhost:6379` |

호스트 포트가 이미 사용 중이면 `.env`의 `FRONTEND_PORT`, `BACKEND_PORT`, `REDIS_PORT`만 변경합니다. 컨테이너 간 통신은 `redis:6379`, `backend:8000`을 사용하고 PostgreSQL host는 필수 `DATABASE_URL`을 따릅니다.

## 역할별 Python 개발환경

Data와 AI 환경은 Docker Compose profile로 분리되어 있습니다. 각 컨테이너는 로컬의 `data/` 또는 `ai/` 코드를 `/app`에 bind mount합니다. Host Python 설치에 의존하지 않고 Container Python을 사용합니다.

### Data 작업자

개발용 data 컨테이너를 계속 실행하려면:

```bash
docker compose --profile data up -d
docker compose exec data bash
```

현재 금융 데이터 구조는 **Azure Blob Raw(JSONL.gz) → Processed Parquet → Features Parquet**입니다. 금융 대용량 파이프라인은 PostgreSQL을 경유하지 않습니다.

Windows CMD에서 프로젝트 루트 기준 준비 상태 확인:

```cmd
run-financial-pipeline.cmd check
```

전체 금융 데이터 파이프라인:

```cmd
run-financial-pipeline.cmd all
```

OS와 무관하게 직접 실행하려면 현재 환경 파일에도 필수 `DATABASE_URL`이 포함되어 있어야 합니다.

```bash
docker compose --profile data run --rm --no-deps data python -m scripts.run_financial_pipeline --stage check --schema-version 1 --feature-version 1
```

데이터 구조와 운영 방법은 [data/README.md](data/README.md), [docs/DATA_ARCHITECTURE.md](docs/DATA_ARCHITECTURE.md), [data/docs/FINANCIAL_PIPELINE_RUNBOOK.md](data/docs/FINANCIAL_PIPELINE_RUNBOOK.md)를 기준으로 합니다.

### AI 작업자

```bash
docker compose --profile ai up -d
docker compose exec ai bash
docker compose exec ai python training/example.py
docker compose exec ai python inference/example.py
```

### Data + AI 전체 환경

```bash
docker compose --profile data --profile ai up -d
```

### Dependency 변경

각 역할의 `requirements.txt`를 수정한 후 해당 이미지를 다시 빌드합니다.

```bash
# Data
docker compose build data
docker compose --profile data up -d

# AI
docker compose build ai
docker compose --profile ai up -d
```

PyTorch나 TensorFlow 같은 대용량 AI 패키지는 실제 모델과 필요한 버전이 확정된 뒤 `ai/requirements.txt`에 추가합니다.

## VS Code Dev Container

Dev Container를 사용하면 VS Code의 Python과 Jupyter Extension이 Host Python이 아니라 역할별 Docker Container의 Python 3.13을 직접 사용합니다. 기존 Docker Compose 명령을 대체하지 않으며 편집기에서 실행과 디버깅, Notebook 사용을 편리하게 만드는 선택 사항입니다.

### 준비

1. Docker Desktop을 설치하고 실행합니다.
2. VS Code에 Microsoft Dev Containers Extension을 설치합니다.
3. VS Code에서 저장소 루트를 엽니다.
4. Command Palette를 엽니다. macOS는 `Cmd + Shift + P`, Windows는 `Ctrl + Shift + P`입니다.
5. `Dev Containers: Reopen in Container`를 실행하고 `SeSAC Data Dev` 또는 `SeSAC AI Dev`를 선택합니다.

처음 연결하거나 `requirements.txt`가 변경된 경우 이미지 빌드와 Extension 설치에 시간이 걸릴 수 있습니다.

### Data 작업자

1. `SeSAC Data Dev`를 선택해 새 VS Code 창을 엽니다.
2. Container 터미널에서 interpreter를 확인합니다.

```bash
python --version
which python
```

3. `data/scripts/`, `data/processing/`, `data/features/`의 Python 파일은 Microsoft Python Extension의 **Run Python File**을 사용합니다.
4. `data/notebooks/`의 `.ipynb` 파일에서는 Container Python 3.13 kernel을 선택합니다.

### AI 작업자

1. `SeSAC AI Dev`를 선택해 새 VS Code 창을 엽니다.
2. `python --version`과 `which python`으로 Container Python을 확인합니다.
3. `training/`, `inference/`의 `.py` 파일에서 **Run Python File**을 사용합니다.
4. `.ipynb` 파일에서는 Container Python kernel을 선택합니다.

### 역할별 창과 일반 Docker 실행의 차이

Dev Container 연결 대상은 파일이 아니라 **VS Code Window 단위**입니다. Data와 AI를 동시에 작업할 때는 저장소를 두 창으로 열어 각각 Data/AI Dev Container에 연결합니다.

- 일반 Docker 실행: VS Code는 Host에서 실행되고 Docker는 애플리케이션/실행 환경을 담당합니다.
- Dev Container: VS Code Extension과 터미널이 Container에 연결되어 Container Python을 직접 사용합니다.

기존 `docker compose up -d`, profile 실행, `docker compose exec` 방식은 그대로 사용할 수 있습니다. Python은 Code Runner의 **Run Code**보다 Microsoft Python Extension의 **Run Python File**을 사용해 interpreter 혼동을 피합니다.

의존성을 변경했다면 역할별 `requirements.txt` 수정 후 `Dev Containers: Rebuild Container`를 실행합니다.

## 개발 중 Hot Reload

`frontend/`와 `backend/`는 컨테이너에 마운트됩니다.

- `frontend/src` 저장 시 Vite가 브라우저 화면을 갱신합니다.
- `backend/app` 저장 시 Uvicorn이 서버를 다시 로드합니다.
- Dockerfile이나 `requirements.txt`, `package.json`, `package-lock.json`을 바꾸면 해당 이미지를 다시 빌드해야 합니다.

```bash
docker compose up --build frontend
docker compose up --build backend
```

## 자주 쓰는 Docker 명령

```bash
docker compose up
docker compose up --build
docker compose up --build -d
docker compose down
docker compose ps
docker compose logs
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f data
docker compose logs -f ai
docker compose restart backend
docker compose up --build -d backend
```

### 로컬 Docker 볼륨 초기화

```bash
docker compose down -v
```

이 명령은 로컬 Redis 및 기타 Compose named volume을 삭제하지만 **Azure PostgreSQL 데이터는 삭제하지 않습니다.** 공용 Azure DB 초기화 용도로 사용하면 안 됩니다.

## 구성 버전

- Frontend: Node.js 24, React, Vite
- Backend: Python 3.13, FastAPI
- Data: Python 3.13 (Compose profile: `data`)
- AI: Python 3.13 (Compose profile: `ai`)
- Database: Azure Database for PostgreSQL Flexible Server (PostgreSQL 17)
- Cache: Redis 8
