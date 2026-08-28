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
