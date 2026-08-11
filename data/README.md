# Data Docker 개발환경

데이터 수집, 전처리, 적재 및 파이프라인 작업을 위한 Python 3.13 개발환경입니다. Host PC의 Python 설치 여부와 관계없이 Docker에서 동일한 의존성을 사용합니다.

## 실행과 접속

명령은 저장소 루트에서 실행합니다. Data profile은 기본 서비스(Frontend, Backend, PostgreSQL, Redis)와 Data 컨테이너를 함께 실행합니다.

```bash
docker compose --profile data up -d
docker compose exec data bash
```

컨테이너는 개발 중 계속 Running 상태를 유지합니다. 로컬 `data/`가 컨테이너 `/app`에 bind mount되므로 코드 변경이 바로 반영됩니다.

## Python Script 실행

```bash
docker compose exec data python scripts/example.py
docker compose exec data python pipelines/example.py
docker compose exec data python --version
```

## VS Code Dev Container

Host Python 없이 VS Code에서 Data Container의 Python 3.13으로 Script와 Notebook을 실행할 수 있습니다.

1. Docker Desktop을 실행합니다.
2. VS Code에 Microsoft의 **Dev Containers** Extension을 설치하고 저장소 루트를 엽니다.
3. Command Palette(macOS `Cmd + Shift + P`, Windows `Ctrl + Shift + P`)에서 `Dev Containers: Reopen in Container`를 실행합니다.
4. `SeSAC Data Dev`를 선택합니다. 선택 화면이 없으면 `Dev Containers: Open Folder in Container...`로 저장소 루트를 다시 엽니다.
5. 연결된 터미널에서 다음을 확인합니다.

   ```bash
   python --version
   which python
   ```

   Python 3.13.x와 `/usr/local/bin/python`이 출력되어야 합니다.
6. `.py` 파일은 Microsoft Python Extension의 **Run Python File** 버튼으로 실행합니다. Code Runner의 **Run Code**는 사용하지 않습니다.
7. `notebooks/`의 `.ipynb` 파일은 셀의 Run 버튼으로 실행합니다. 필요하면 `Select Kernel` → `Python Environments`에서 Container Python 3.13을 선택합니다.

VS Code 터미널은 Data Container의 shell이므로 다음처럼 직접 실행할 수도 있습니다.

```bash
python scripts/example.py
python pipelines/example.py
python -c "import ipykernel; print(ipykernel.__version__)"
```

Dev Container는 VS Code Window 단위로 연결됩니다. AI도 함께 작업한다면 저장소를 별도 창에서 열고 `SeSAC AI Dev`에 연결합니다.

## Dependency 추가

`data/requirements.txt`에 필요한 패키지와 버전을 추가한 뒤 이미지를 다시 빌드합니다.

```bash
docker compose build data
docker compose --profile data up -d
```

Dev Container를 사용 중이면 `data/requirements.txt` 수정 후 Command Palette의 `Dev Containers: Rebuild Container`로 이미지를 다시 빌드합니다. VS Code Notebook 실행에는 `ipykernel`을 사용하며, 브라우저 기반 JupyterLab은 포함하지 않습니다.

기존 CLI 방식도 그대로 지원합니다.

```bash
docker compose --profile data up -d
docker compose exec data python scripts/example.py
docker compose exec data python pipelines/example.py
```

## PostgreSQL / Redis 접근

Compose 네트워크에서는 `localhost` 대신 서비스명을 사용합니다. 연결 문자열은 `.env` 또는 `.env.example` 형식을 따르며 컨테이너에 `DATABASE_URL`, `REDIS_URL`로 전달됩니다.

- PostgreSQL: `postgres:5432`
- Redis: `redis:6379`

실제 Secret은 이미지, 소스 코드 또는 Compose 파일에 기록하지 않습니다.

## 상태 확인과 종료

```bash
docker compose ps
docker compose logs -f data
docker compose down
```

`docker compose down`은 컨테이너를 제거하지만 PostgreSQL과 Redis의 named volume 데이터는 유지합니다.
