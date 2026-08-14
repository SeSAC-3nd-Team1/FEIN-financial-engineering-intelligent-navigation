# SeSAC 3차 프로젝트 1팀

Docker Compose 기반의 공통 로컬 개발환경입니다. Docker Desktop만 있으면 프런트엔드, 백엔드, PostgreSQL, Redis를 같은 버전으로 실행할 수 있습니다.

## Development setup

### 1. 준비

1. [Git](https://git-scm.com/)과 [Docker Desktop](https://www.docker.com/products/docker-desktop/)을 설치합니다.
2. Docker Desktop을 실행하고 엔진이 준비될 때까지 기다립니다.
3. 저장소를 복제하고 `develop` 브랜치로 이동합니다.

```bash
git clone https://github.com/SeSAC-3nd-Team1/SeSAC-3nd-Team1-project.git
cd SeSAC-3nd-Team1-project
git switch develop
```

Windows에서는 PowerShell, macOS에서는 Terminal에서 아래 명령을 그대로 사용할 수 있습니다. WSL2는 필수가 아닙니다.

### 2. 환경 변수

예제 파일을 복사해 로컬 전용 `.env`를 만듭니다.

```bash
cp .env.example .env
```

PowerShell에서는 다음 명령을 사용할 수 있습니다.

```powershell
Copy-Item .env.example .env
```

외부 API를 사용하는 작업이라면 `.env`의 빈 Secret 항목을 채웁니다. `.env`는 Git에서 제외되며 실제 키를 소스, Dockerfile, Compose 파일, 문서에 기록하면 안 됩니다.

### 3. 기본 개발환경 실행

```bash
docker compose up -d
```

최초 실행이거나 Dockerfile 및 dependency가 변경되었다면 `docker compose up -d --build`를 사용합니다. 기본 실행에는 Frontend, Backend, PostgreSQL, Redis만 포함되며 Data와 AI는 실행되지 않습니다. 모든 서비스가 healthy 상태가 되면 개발을 시작할 수 있습니다.

| 서비스 | 접속/확인 위치 |
| --- | --- |
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 |
| Backend health | http://localhost:8000/health |
| Dependency health | http://localhost:8000/health/dependencies |
| Swagger UI | http://localhost:8000/docs |
| PostgreSQL | `localhost:5432` (`app` / `app`) |
| Redis | `localhost:6379` |

호스트 포트가 이미 사용 중이면 `.env`의 `FRONTEND_PORT`, `BACKEND_PORT`, `POSTGRES_PORT`, `REDIS_PORT`만 변경합니다. 컨테이너 간 통신은 항상 `postgres:5432`, `redis:6379`, `backend:8000`을 사용합니다.

## 역할별 Python 개발환경

Data와 AI 환경은 Docker Compose profile로 분리되어 있습니다. 각 컨테이너는 일회성 작업이 아니라 개발 중 계속 Running 상태를 유지하며, 로컬의 `data/` 또는 `ai/` 코드가 `/app`에 bind mount되어 저장 즉시 반영됩니다. Host PC에 Python 3.13을 설치할 필요가 없으며 Python은 `docker compose exec`로 실행합니다.

### Data 작업자

기본 서비스와 Data 환경을 함께 실행합니다.

```bash
docker compose --profile data up -d
docker compose exec data bash
docker compose exec data python scripts/example.py
docker compose exec data python pipelines/example.py
```

PostgreSQL 데이터 모델, Alembic migration, UPSERT 적재 및 Parquet export 사용법은 [data/README.md](data/README.md)를 참고합니다.

### AI 작업자

기본 서비스와 AI 환경을 함께 실행합니다.

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

PyTorch나 TensorFlow 같은 대용량 AI 패키지는 초기 환경에 포함하지 않습니다. 실제 모델과 필요한 버전이 확정된 뒤 `ai/requirements.txt`에 추가합니다.

## VS Code Dev Container

Dev Container를 사용하면 VS Code의 Python과 Jupyter Extension이 Host Python이 아니라 역할별 Docker Container의 Python 3.13을 직접 사용합니다. 기존 Docker Compose 명령을 대체하지 않으며, 편집기에서 실행과 디버깅, Notebook 사용을 편리하게 만드는 선택 사항입니다.

### 준비

1. Docker Desktop을 설치하고 실행합니다.
2. VS Code에 Microsoft의 [Dev Containers Extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)을 설치합니다.
3. VS Code에서 저장소 루트를 엽니다.
4. Command Palette를 엽니다. macOS는 `Cmd + Shift + P`, Windows는 `Ctrl + Shift + P`입니다.
5. `Dev Containers: Reopen in Container`를 실행하고 `SeSAC Data Dev` 또는 `SeSAC AI Dev`를 선택합니다.

처음 연결하거나 `requirements.txt`가 변경된 경우 이미지 빌드와 Extension 설치에 시간이 걸릴 수 있습니다. 설정 선택 화면이 나타나지 않으면 `Dev Containers: Open Folder in Container...`로 저장소 루트를 다시 선택합니다.

### Data 작업자

1. `SeSAC Data Dev`를 선택해 새 VS Code 창을 엽니다.
2. Container 터미널에서 interpreter를 확인합니다.

   ```bash
   python --version
   which python
   ```

   Python 3.13.x와 `/usr/local/bin/python`이 출력되어야 합니다.
3. `scripts/` 또는 `pipelines/`의 `.py` 파일을 열고 Microsoft Python Extension의 **Run Python File** 버튼을 사용합니다.
4. `notebooks/`의 `.ipynb` 파일을 열고 셀의 Run 버튼을 사용합니다. Kernel 선택이 필요하면 `Select Kernel` → `Python Environments`에서 Container의 Python 3.13을 선택합니다.

### AI 작업자

1. `SeSAC AI Dev`를 선택해 새 VS Code 창을 엽니다.
2. 터미널에서 `python --version`과 `which python`을 실행해 Python 3.13.x와 `/usr/local/bin/python`을 확인합니다.
3. `training/` 또는 `inference/`의 `.py` 파일에서 Microsoft Python Extension의 **Run Python File** 버튼을 사용합니다.
4. `.ipynb` 파일에서는 셀의 Run 버튼을 사용하고, 필요하면 Container Python 3.13 kernel을 선택합니다.

### 역할별 창과 일반 Docker 실행의 차이

Dev Container 연결 대상은 파일이 아니라 **VS Code Window 단위**입니다. Data와 AI를 동시에 작업할 때는 저장소를 두 창으로 열어 Window 1은 `SeSAC Data Dev`, Window 2는 `SeSAC AI Dev`에 연결합니다. 파일을 열 때마다 Container가 자동 전환되지는 않습니다.

- 일반 Docker 실행: VS Code는 Host에서 실행되고 Docker는 애플리케이션과 실행 환경을 담당합니다.
- Dev Container: VS Code의 Extension과 터미널이 Container에 연결되어 Container Python을 직접 사용합니다.

기존 `docker compose up -d`, profile 실행, `docker compose exec` 방식은 그대로 사용할 수 있습니다. VS Code에 Code Runner Extension이 설치되어 있더라도 Python은 Code Runner의 **Run Code**가 아닌 Microsoft Python Extension의 **Run Python File**로 실행해야 interpreter 혼동을 피할 수 있습니다.

의존성을 변경했다면 역할별 `requirements.txt` 수정 후 Command Palette에서 `Dev Containers: Rebuild Container`를 실행합니다.

## 개발 중 Hot Reload

`frontend/`와 `backend/`는 컨테이너에 마운트됩니다.

- `frontend/src` 파일을 저장하면 Vite가 브라우저 화면을 갱신합니다.
- `backend/app`의 Python 파일을 저장하면 Uvicorn이 서버를 다시 로드합니다.
- Dockerfile이나 `requirements.txt`, `package.json`, `package-lock.json`을 바꾸면 해당 이미지를 다시 빌드해야 합니다.

```bash
docker compose up --build frontend
docker compose up --build backend
```

## 자주 쓰는 Docker 명령

```bash
# 기존 이미지로 실행
docker compose up

# 이미지를 다시 빌드하고 실행
docker compose up --build

# 백그라운드 실행
docker compose up --build -d

# 컨테이너 중지 및 제거 (DB/Redis 데이터는 유지)
docker compose down

# 서비스 상태 확인
docker compose ps

# 전체 로그 / 실시간 서비스 로그
docker compose logs
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f data
docker compose logs -f ai

# 한 서비스만 재시작
docker compose restart backend

# 한 서비스만 다시 빌드하여 실행
docker compose up --build -d backend
```

### 데이터베이스 초기화

```bash
docker compose down -v
```

> 주의: 이 명령은 PostgreSQL과 Redis의 named volume까지 삭제합니다. 로컬 데이터가 모두 사라져도 되는 경우에만 실행하세요.

## 구성 버전

- Frontend: Node.js 24, React, Vite
- Backend: Python 3.13, FastAPI
- Data: Python 3.13 (Compose profile: `data`)
- AI: Python 3.13 (Compose profile: `ai`)
- Database: PostgreSQL 17
- Cache: Redis 8
