# 환경 변수 관리 가이드

FE!N 프로젝트의 로컬 환경 변수는 저장소 루트의 `.env` 하나로 관리한다. Docker Compose는 별도 `--env-file` 옵션 없이 이 파일을 자동으로 읽는다.

## 최초 설정

저장소를 받은 뒤 예제 파일을 복사한다.

```bash
cp .env.example .env
```

PowerShell에서는 다음 명령을 사용한다.

```powershell
Copy-Item .env.example .env
```

`.env.example`에는 변수 이름, 안전한 기본값, 한국어 설명만 둔다. 실제 비밀번호와 API 키는 `.env`에만 입력한다.

## 파일 정책

- 로컬 실행은 루트 `.env`만 사용한다.
- `.env.azure` 같은 서비스별 Secret 파일은 만들거나 사용하지 않는다.
- 기존 `.env.azure`의 값은 `.env`로 옮긴 뒤 중복 파일을 삭제한다.
- `.env`와 `.env.*`는 `.gitignore`로 제외한다. `.env.example`만 버전 관리한다.
- 실제 Secret을 코드, Dockerfile, Compose, 문서, Issue, PR, 채팅, 로그에 기록하지 않는다.
- 노출된 Secret은 파일에서 지우는 것으로 끝내지 않고 해당 서비스에서 즉시 회전한다.

## 주요 필수·선택 변수

| 구분 | 변수 | 필요한 경우 |
| --- | --- | --- |
| 공용 PostgreSQL | `DATABASE_URL` | 모든 Docker Compose 실행에서 필수 |
| Backend 인증 | `JWT_SECRET` | 로그인·인증 기능 사용 시 필수 |
| ACS Email | `ACS_EMAIL_CONNECTION_STRING`, `ACS_EMAIL_SENDER_ADDRESS` | 회원가입 이메일 인증 사용 시 필수 |
| 이메일 OTP | `EMAIL_OTP_SECRET` | OTP HMAC 및 가입 증명 발급 시 필수 |
| 공공데이터포털 | `DATA_GO_KR_API_KEY` | 금융위원회 데이터 수집 시 필수 |
| OpenDART | `OPENDART_API_KEY` | 기업·재무·공시 데이터 수집 시 필수 |
| 한국은행 ECOS | `ECOS_API_KEY` | 거시경제 데이터 수집 시 필수 |
| KIS Open API | `KIS_APP_KEY`, `KIS_APP_SECRET` | 현재가·실시간 시세 조회 시 필수 |
| NAVER API HUB | `NAVER_API_HUB_CLIENT_ID`, `NAVER_API_HUB_CLIENT_SECRET` | 한국 금융 뉴스 조회 시 필수 |
| Azure OpenAI 분석 | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, 기능별 deployment 변수 | 전략 추천·리밸런싱 제안·투자 비교 기능 사용 시 필수. 투자성향 점수 계산에는 불필요 |
| Azure OpenAI 챗봇 | `AZURE_OPENAI_CHATBOT_ENDPOINT`, `AZURE_OPENAI_CHATBOT_API_KEY`, `AZURE_OPENAI_CHATBOT_DEPLOYMENT`, `AZURE_OPENAI_CHATBOT_API_VERSION` | 별도 Azure OpenAI 리소스의 챗봇 기능 사용 시 필수 |
| Azure Blob | `AZURE_STORAGE_ACCOUNT_NAME` | 실제 Azure Blob 파이프라인 실행 시 필수 |

전체 변수와 기본값은 [`.env.example`](../.env.example)을 기준으로 한다. 사용하지 않는 외부 연동의 키는 비워둘 수 있지만 `DATABASE_URL`은 비워둘 수 없다.

이메일 인증을 사용할 때 위 세 값을 모두 설정해야 한다. TTL·재발송·시도 횟수·시간당 한도는
`EMAIL_OTP_TTL_SECONDS`, `EMAIL_OTP_RESEND_SECONDS`, `EMAIL_OTP_MAX_ATTEMPTS`,
`EMAIL_OTP_HOURLY_LIMIT`, `EMAIL_OTP_IP_HOURLY_LIMIT`,
`EMAIL_VERIFICATION_TOKEN_TTL_SECONDS`로 조정한다. 실제 ACS 연결 문자열과
OTP secret은 로그나 버전 관리 파일에 남기지 않는다.

## PostgreSQL URL

형식은 다음과 같다.

```dotenv
DATABASE_URL=postgresql://<USER>:<PASSWORD>@<HOST>:5432/<DATABASE>?sslmode=require
```

비밀번호의 `@`, `:`, `/`, `%`, `#`, `?` 같은 문자는 percent-encoding한다. 실제 URL을 확인할 때는 전체 값을 출력하지 말고 host와 database 이름만 확인한다.

```bash
docker compose exec backend python -c "from app.core.config import settings; from urllib.parse import urlsplit; u=urlsplit(settings.database_url); print('DB HOST =', u.hostname); print('DB =', u.path.lstrip('/'))"
```

## 실행과 확인

```bash
docker compose up -d --build
docker compose ps
curl --fail http://localhost:8000/health/dependencies
```

정상 응답은 다음과 같다.

```json
{"postgres":"ok","redis":"ok"}
```

환경 변수를 변경했다면 기존 컨테이너에 자동 반영되지 않을 수 있으므로 해당 서비스를 다시 생성한다.

```bash
docker compose up -d --force-recreate
```

공용 Azure DB migration 절차와 테스트 제한은 [Azure PostgreSQL 단일 프로젝트 DB 가이드](AZURE_POSTGRESQL_DEV.md)를 따른다.

## Production Container Apps 배포 환경변수

Production 배포는 GitHub Actions의 `production` Environment와 Azure Key Vault `kv-fein`을 함께 사용한다. 실제 Secret 값은 workflow, 저장소, Issue, PR, 로그에 기록하지 않는다.

배포의 핵심 의존성은 PostgreSQL, 내부 Redis, ACS Email, KIS다. NAVER 뉴스와 Azure OpenAI 기능은 해당 credential이 있을 때 활성화되는 선택 연동이며, 값이 없다는 이유만으로 Frontend/Backend 전체 Production 배포를 차단하지 않는다.

### 반드시 GitHub production Environment에 있어야 하는 값

Azure 로그인과 배포 자체에 필요한 값이다.

**Secrets**

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `DATABASE_URL`

**Variables**

- `ACR_NAME`
- `AZURE_RESOURCE_GROUP`
- `FRONTEND_APP_NAME`
- `BACKEND_APP_NAME`

### Production Redis

Production에서는 로컬 Docker Compose 주소인 `redis://redis:6379/0`을 사용하지 않는다.

workflow가 Backend와 동일한 Azure Container Apps Environment에 `ca-redis-fein-vnet`을 생성하거나 기존 App을 재사용하고, internal TCP 6379만 활성화한다. 기존 Redis App을 재사용할 때는 Backend와 `managedEnvironmentId`가 동일한지 확인하며 다르면 배포를 실패 처리한다.

Backend에는 다음 주소가 자동 설정된다.

```text
REDIS_URL=redis://ca-redis-fein-vnet:6379/0
```

따라서 Production GitHub Environment에 별도 `REDIS_URL` Secret을 등록하지 않는다. 이 Redis는 OTP 상태, rate limit, 가격·뉴스 cache 등 휘발성 상태용 MVP 구성이다. 장기 상용 운영에서는 인증/ACL 적용 또는 Azure Managed Redis 전환을 검토한다.

### ACS / KIS Secret bootstrap

회원가입과 실제 시세 흐름에 필요한 ACS/KIS credential은 다음 우선순위로 설정한다.

1. GitHub `production` Environment Secret이 있으면 해당 값을 사용한다.
2. GitHub에 값이 없으면 Azure Key Vault `kv-fein`의 Secret을 Container App Key Vault reference로 연결한다.

GitHub에서 선택적으로 등록할 수 있는 이름은 다음과 같다.

- `ACS_EMAIL_CONNECTION_STRING`
- `KIS_APP_KEY`
- `KIS_APP_SECRET`

Key Vault 기본 Secret 이름은 다음과 같고 Variables로 재정의할 수 있다.

| Variable | 기본값 | 용도 |
| --- | --- | --- |
| `KEY_VAULT_NAME` | `kv-fein` | Production Key Vault 이름 |
| `ACS_EMAIL_KV_SECRET` | `email-service-key` | ACS Email 연결 credential Secret 이름 |
| `KIS_APP_KEY_KV_SECRET` | `kis-app-key` | KIS App Key Secret 이름 |
| `KIS_APP_SECRET_KV_SECRET` | `kis-app-secret` | KIS App Secret Secret 이름 |

GitHub Secret이 비어 Key Vault reference가 필요하면 workflow가 Backend Container App의 system-assigned managed identity를 활성화한다. Key Vault가 RBAC 모드이면 `Key Vault Secrets User`, access-policy 모드이면 secret `get/list` 권한을 부여하려고 시도한다. 배포 주체에 해당 권한 부여 권한이 없으면 Secret 값을 우회해서 노출하지 않고 명시적으로 배포를 실패 처리한다.

Container App 내부 Secret 이름은 Azure 제한을 고려해 `acs-email`, `kis-key`, `kis-secret`처럼 짧게 유지하고 Backend 환경변수에서는 `secretref:`로 참조한다.

### Backend 인증 / 이메일 OTP Secret

- `JWT_SECRET`
- `EMAIL_OTP_SECRET`

위 두 값은 GitHub `production` Secrets에 직접 등록할 수 있다. GitHub 값이 없고 기존 Backend 환경에도 값이 없으면 workflow가 충분히 긴 난수를 생성해 Container App Secret으로 저장한다. 이후 배포에서는 기존 값을 유지한다.

### 선택 연동: NAVER / Azure OpenAI

다음 Secret은 해당 기능을 Production에서 활성화할 때 GitHub `production` Environment에 등록한다.

- `NAVER_API_HUB_CLIENT_ID`
- `NAVER_API_HUB_CLIENT_SECRET`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_CHATBOT_API_KEY`

값이 있으면 workflow가 Container App Secret으로 저장하고 Backend 환경변수에 `secretref:`를 연결한다. 값이 없으면 해당 기능은 Backend의 기존 unavailable/error 정책을 따르지만 전체 Production 배포는 계속할 수 있다.

비민감 설정은 GitHub `production` Variables로 override할 수 있다.

| 이름 | 의미 |
| --- | --- |
| `ACS_EMAIL_SENDER_ADDRESS` | ACS Email Communication Services MailFrom 주소 |
| `AZURE_OPENAI_ENDPOINT` | 전략추천·리밸런싱·비교용 Azure OpenAI endpoint |
| `AZURE_OPENAI_RECOMMENDATION_DEPLOYMENT` | 전략 추천 deployment 이름 |
| `AZURE_OPENAI_REBALANCING_DEPLOYMENT` | 리밸런싱 deployment 이름 |
| `AZURE_OPENAI_COMPARISON_DEPLOYMENT` | 포트폴리오 비교 deployment 이름 |
| `AZURE_OPENAI_CHATBOT_ENDPOINT` | 챗봇 전용 Azure OpenAI endpoint |
| `AZURE_OPENAI_CHATBOT_DEPLOYMENT` | 챗봇 deployment 이름 |

현재 프로젝트에서 확정된 MailFrom, 공통 Azure OpenAI endpoint, 챗봇 endpoint/deployment에는 workflow의 안전한 비민감 기본값이 있다. 반면 추천·리밸런싱·비교 deployment 이름은 확정된 값이 없으므로 추측해서 채우지 않는다. 해당 기능을 활성화하려면 실제 Azure deployment 이름을 Variable에 명시한다.

Frontend CORS origin은 고정 문자열로 저장하지 않는다. workflow가 `FRONTEND_APP_NAME`의 실제 Container App FQDN을 Azure에서 조회한 뒤 `https://<fqdn>`을 `CORS_ORIGINS`로 설정한다.

TTL, timeout, cache, API version 같은 비민감 운영 기본값은 workflow에서 Backend 기본값과 동일하게 명시적으로 설정한다. 배포 후에는 Redis/Frontend/Backend의 `latestRevisionName`과 `latestReadyRevisionName`이 동일해질 때까지 확인하고, 최신 revision이 Ready 상태가 되지 않으면 workflow를 실패 처리한다.

### 모델 snapshot 변수

`MODEL_RECOMMENDATION_SNAPSHOT_PATH`, `LOSS_AVOIDANCE_SNAPSHOT_PATH`는 실제 모델 artifact가 Container App에서 읽을 수 있도록 volume/mount 또는 이미지 포함 경로가 준비된 뒤 설정한다. Production deploy는 Azure Feature Store에서 생성한 v2 artifact를 Backend image의 `/model-artifacts`에 포함하고 `MODEL_RECOMMENDATION_SNAPSHOT_PATH=/model-artifacts/risk-adjusted-momentum-v2.json`을 설정한다. 경로만 환경변수로 추가하고 실제 파일을 제공하는 단계가 없는 구성은 사용하지 않는다.

Production에서는 저장소의 시연용 snapshot이 실제 결과처럼 노출되지 않도록 `MODEL_RECOMMENDATION_ALLOW_FALLBACK=false`를 강제한다. 실제 generated snapshot이 없거나 stale하면 모델 추천 API가 명시적으로 unavailable 상태를 반환한다. `MODEL_RECOMMENDATION_STALE_AFTER_DAYS=7`을 기본 운영 기준으로 사용한다.
