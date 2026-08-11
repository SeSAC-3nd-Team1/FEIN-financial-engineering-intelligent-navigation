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

### 3. 전체 환경 실행

```bash
docker compose up --build
```

최초 빌드가 끝나고 모든 서비스가 healthy 상태가 되면 개발을 시작할 수 있습니다.

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
- Database: PostgreSQL 17
- Cache: Redis 8
