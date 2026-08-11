# AI Docker 개발환경

모델 개발, 학습, 평가 및 추론 작업을 위한 Python 3.13 개발환경입니다. Host PC의 Python 설치 여부와 관계없이 Docker에서 동일한 의존성을 사용합니다.

## 실행과 접속

명령은 저장소 루트에서 실행합니다. AI profile은 기본 서비스(Frontend, Backend, PostgreSQL, Redis)와 AI 컨테이너를 함께 실행합니다.

```bash
docker compose --profile ai up -d
docker compose exec ai bash
```

컨테이너는 개발 중 계속 Running 상태를 유지합니다. 로컬 `ai/`가 컨테이너 `/app`에 bind mount되므로 코드 변경이 바로 반영됩니다.

## Training / Inference 실행

```bash
docker compose exec ai python training/example.py
docker compose exec ai python inference/example.py
docker compose exec ai python --version
```

## Dependency 추가

`ai/requirements.txt`에 필요한 패키지와 버전을 추가한 뒤 이미지를 다시 빌드합니다.

```bash
docker compose build ai
docker compose --profile ai up -d
```

PyTorch와 TensorFlow 같은 대용량 패키지는 초기 환경에 포함하지 않습니다. 실제 모델, CPU/GPU 실행 방식 및 호환 버전이 확정된 뒤 추가합니다.

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
