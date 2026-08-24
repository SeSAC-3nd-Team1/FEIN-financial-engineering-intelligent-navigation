# SeSAC 3차 프로젝트 1팀

Docker Compose 기반의 공통 개발환경입니다. 서비스 DB는 로컬 PostgreSQL과 팀 공용 Azure Database for PostgreSQL 중 하나를 `DATABASE_URL`로 선택할 수 있습니다.

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

외부 API를 사용하는 작업이라면 `.env`의 빈 Secret 항목을 채웁니다. `.env`는 Git에서 제외되며 실제 키를 소스, Dockerfile, Compose 파일, 문서에 기록하면 안 됩니다.

PostgreSQL은 `.env`의 `DATABASE_URL` 한 줄로 전환합니다. 기본 예시는 로컬 Docker DB이며, 팀 공용 Azure Database for PostgreSQL을 사용할 때는 `?sslmode=require`가 포함된 Azure URL로 교체합니다. 실제 Azure 사용자명·비밀번호·호스트는 GitHub에 올리지 않습니다. 전체 준비 절차와 Portal/CLI 작업은 [Azure PostgreSQL 공용 개발 DB 가이드](docs/AZURE_POSTGRESQL_DEV.md)를 따릅니다.

운영/공유 환경에서는 `JWT_SECRET`을 긴 무작위 값으로 교체합니다. KIS는 `KIS_APP_KEY`/`KIS_APP_SECRET`으로 **현재가만 조회**하며 KIS 주문 API는 사용하지 않습니다. OAuth token은 Redis에서 만료시간과 함께 공유해 요청별 재발급을 방지합니다. 가상계좌 초기금은 `VIRTUAL_ACCOUNT_INITIAL_CASH` 정책 값으로 설정합니다.

한국 금융 뉴스는 NAVER Cloud Platform의 NAVER API HUB Search News API를 Backend에서만 호출합니다. 로컬 `.env`에 `NAVER_API_HUB_CLIENT_ID`와 `NAVER_API_HUB_CLIENT_SECRET`을 설정하고 실제 값은 커밋하거나 로그에 출력하지 않습니다. 기본 검색어는 `NEWS_SEARCH_QUERY=증시`, Redis cache TTL은 `NEWS_CACHE_TTL_SECONDS=300`입니다.

Azure Blob을 사용하는 Data 작업은 별도의 로컬 `.env.azure` 설정과 Azure CLI/Entra ID 인증을 사용합니다. Shared Key 기반 실제 Azure connection string은 사용하지 않습니다.

### 3. 기본 개발환경 실행

```bash
docker compose up -d
```

최초 실행이거나 Dockerfile 및 dependency가 변경되었다면 `docker compose up -d --build`를 사용합니다. 기본 실행에는 Frontend, Backend, PostgreSQL, Redis와 일회성 `db-init`이 포함됩니다. `db-init`은 Backend보다 먼저 Alembic migration을 적용하고 `.env`의 `SIGNUP_TERMS_*` 개발용 약관을 멱등 seed한 뒤 종료합니다. Data와 AI 작업용 장기 실행 컨테이너는 profile로 분리됩니다.

DB 준비만 다시 실행하려면:

```bash
docker compose up -d postgres redis
docker compose run --rm db-init
docker compose up -d --build backend frontend
```

동일한 `SIGNUP_TERMS_VERSION`으로 `db-init`을 반복해도 `(term_code, version)` UNIQUE와 `ON CONFLICT DO NOTHING` 때문에 중복 약관이 생기지 않습니다. 기본 version의 `dev-` prefix는 로컬 개발 데이터임을 나타냅니다. 운영 약관은 승인된 별도 version·효력 시각·불변 본문 URL을 명시적으로 설정해야 하며 Compose 기본값을 사용하지 않습니다.

### Azure PostgreSQL 공용 개발 DB 실행

`.env`의 `DATABASE_URL`을 팀에서 전달받은 Azure URL로 설정한 뒤 로컬 PostgreSQL을 제외하고 실행합니다.

```bash
docker compose up -d --build frontend backend redis
docker compose ps
curl --fail http://localhost:8000/health/dependencies
```

`backend`가 의존하는 일회성 `db-init`은 자동으로 Alembic과 약관 seed를 적용합니다. 여러 개발자가 동시에 실행해도 PostgreSQL advisory lock으로 초기화가 직렬화되며 기존 사용자·계좌·주문 데이터는 삭제하거나 덮어쓰지 않습니다. 명시적으로 migration만 준비할 때는 다음 명령을 사용합니다.

```bash
docker compose run --rm --no-deps db-init
```

Azure 모드에서는 전체 서비스를 뜻하는 `docker compose up`을 사용하면 사용하지 않는 로컬 `postgres`도 함께 시작됩니다. 공용 DB 연결에는 영향이 없지만 불필요한 컨테이너를 피하려면 위의 서비스 목록을 그대로 사용합니다.

Backend 테스트:

```bash
docker compose run --rm --no-deps backend pytest -q
```

Seeded PostgreSQL/Redis E2E 테스트:

```bash
docker compose run --rm db-init
docker compose exec -T backend env RUN_INTEGRATION=1 pytest -q tests/test_integration_flow.py
```

E2E는 `GET /auth/terms`부터 회원가입 동의 저장, 계좌·전략·매수·멱등 재시도·포트폴리오·매도·원장 정합성까지 확인합니다. 생성한 사용자와 가상거래 관계 및 전용 Redis 가격 key만 테스트 종료 시 FK 역순으로 제거하며 개발 데이터 전체를 삭제하지 않습니다.

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

투자성향 분석은 인증된 `POST /api/v1/investor-profile/analyze` 요청으로 처리한다. Backend는 `v1` 설문의 8개 문항 ID와 선택지 ID를 검증한 뒤 Azure OpenAI에 전달하고, 모델 분석이 끝나면 같은 HTTP 요청에서 5단계 투자유형과 설명을 구조화된 JSON으로 반환한다. 답변과 분석 결과는 DB에 저장하지 않는다. 로컬 실행 전 `.env`에 `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`를 설정한다.

Frontend 가상투자 화면은 FastAPI만 호출한다. `/accounts/me`로 동적 계좌 ID를 얻고 `/portfolio` 한 번으로 현금·보유종목·현재 평가를 조회한다. 시장가 BUY/SELL은 UUID idempotency key와 함께 `/orders`로 보내며 성공 후 portfolio/orders/executions를 다시 조회한다. KIS는 Backend `MarketService`의 가격 공급자로만 사용하고, 가상계좌·주문·체결·포지션·현금원장은 PostgreSQL에서 관리한다. 브라우저 bundle에는 KIS key/secret이나 KIS 직접 호출 URL이 포함되지 않는다.

| 서비스 | 접속/확인 위치 |
| --- | --- |
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 |
| Backend health | http://localhost:8000/health |
| Dependency health | http://localhost:8000/health/dependencies |
| Swagger UI | http://localhost:8000/docs |
| PostgreSQL | Local 모드: `localhost:5432` (`app` / `app`), Azure 모드: `.env`의 원격 host |
| Redis | `localhost:6379` |

호스트 포트가 이미 사용 중이면 `.env`의 `FRONTEND_PORT`, `BACKEND_PORT`, `POSTGRES_PORT`, `REDIS_PORT`만 변경합니다. Local 모드의 컨테이너 간 통신은 `postgres:5432`, `redis:6379`, `backend:8000`을 사용하고, Azure 모드의 PostgreSQL host는 `DATABASE_URL`을 따른다.

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

OS와 무관하게 직접 실행하려면:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.run_financial_pipeline --stage check --schema-version 1 --feature-version 1
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

### 데이터베이스 초기화

```bash
docker compose down -v
```

주의: 이 명령은 PostgreSQL과 Redis named volume까지 삭제합니다. 로컬 데이터가 모두 사라져도 되는 경우에만 실행하세요.

## 구성 버전

- Frontend: Node.js 24, React, Vite
- Backend: Python 3.13, FastAPI
- Data: Python 3.13 (Compose profile: `data`)
- AI: Python 3.13 (Compose profile: `ai`)
- Database: PostgreSQL 17
- Cache: Redis 8
