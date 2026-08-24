# Azure PostgreSQL 단일 프로젝트 DB 가이드

FE!N 프로젝트의 일반 개발·시연용 관계형 DB는 **Azure Database for PostgreSQL Flexible Server 1개로 통일**한다. 로컬 Docker PostgreSQL은 일반 개발 경로에서 사용하지 않는다.

Azure Blob Storage의 Raw / Processed / Features 데이터와 Redis는 별도 계층이며 이 정책의 대상이 아니다.

## 핵심 정책

- Backend, migration job, Data, AI는 모두 동일한 `DATABASE_URL`을 사용한다.
- `DATABASE_URL`은 필수다. 없거나 빈 값이면 Docker Compose가 즉시 실패한다.
- 로컬 PostgreSQL fallback은 제공하지 않는다.
- 실제 Azure Connection String은 `.env` 또는 배포 Secret에만 둔다.
- 비밀번호의 `@`, `:`, `/`, `%`, `#`, `?` 같은 문자는 percent-encoding해야 한다.
- URL 자체를 채팅, Issue, PR, 로그에 붙이지 않는다.
- 일반 개발과 발표/시연은 같은 프로젝트 DB를 사용한다.
- 일반 `docker compose up`은 migration을 실행하지 않는다.
- migration 담당자가 임시/CI PostgreSQL 검증과 `develop` 반영 후 공용 Azure DB에 명시적으로 적용한다.
- 파괴적 테스트가 필요할 때만 별도 임시 PostgreSQL을 테스트 실행 범위에서 사용한다.

## 팀원이 새 PC에서 시작하기

```bash
git clone https://github.com/SeSAC-3nd-Team1/SeSAC-3nd-Team1-project.git
cd SeSAC-3nd-Team1-project
git switch develop
cp .env.example .env
```

`.env`의 `DATABASE_URL`에 팀 공용 Azure PostgreSQL URL을 입력한다.

```env
DATABASE_URL=postgresql://<USER>:<PASSWORD>@<HOST>:5432/<DATABASE>?sslmode=require
```

실제 값은 Git에 커밋하지 않는다. `DATABASE_URL`이 비어 있으면 `docker compose`는 실행되지 않는다.

## 기본 실행

```bash
docker compose up -d --build

docker compose ps
curl --fail http://localhost:8000/health/dependencies
```

정상 결과:

```json
{"postgres":"ok","redis":"ok"}
```

기본 실행 서비스는 Frontend, Backend, Redis다. 로컬 PostgreSQL 컨테이너와 migration job은 생성하지 않으며 Backend는 현재 공용 Azure schema에 연결만 한다.

## Migration과 초기 데이터

DB schema 변경 담당자는 임시/CI PostgreSQL에서 먼저 migration을 검증하고, 해당 변경이 `develop`에 반영된 뒤 다음 명령으로 공용 Azure DB에 적용한다.

```bash
git switch develop
git pull origin develop
docker compose --profile migration run --rm --no-deps db-init
```

feature branch에서 이 명령을 공용 Azure DB 대상으로 실행하지 않는다. 아직 merge되지 않은 migration이 팀 공용 schema에 먼저 적용될 수 있다.

`db-init`은 다음 순서로 동작한다.

1. `DATABASE_URL` 대상 Azure PostgreSQL 연결을 제한적으로 재시도한다.
2. transaction 범위 PostgreSQL advisory lock을 획득한다.
3. 기존 Alembic history에 대해 `upgrade head`를 실행한다.
4. `(term_code, version)` 충돌을 무시하는 약관 seed를 실행한다.
5. 성공하면 commit하고 lock을 해제한다. 실패하면 전체 transaction을 rollback한다.

이미 기록된 Alembic revision은 재적용되지 않으며 기존 약관, 사용자, 가상계좌, 포지션, 주문, 체결, 현금원장을 삭제하거나 덮어쓰지 않는다.

현재 schema와 연결 확인:

```bash
docker compose run --rm --no-deps data python -m scripts.check_db
docker compose run --rm --no-deps data alembic current
```

## 현재 연결 DB 확인

비밀번호를 출력하지 않고 Backend가 실제 어느 DB를 보는지 확인한다.

```bash
docker compose exec backend python -c "from app.core.config import settings; from urllib.parse import urlsplit; u=urlsplit(settings.database_url); print('DB HOST =', u.hostname); print('DB =', u.path.lstrip('/'))"
```

정상이라면 `DB HOST`가 Azure Flexible Server FQDN이어야 한다.

예:

```text
DB HOST = <server>.postgres.database.azure.com
DB = <database>
```

다음처럼 나오면 안 된다.

```text
DB HOST = postgres
DB = app
```

## 회원가입·로그인·영속성 검증

1. `http://localhost:5173`에서 고유한 개발용 사용자를 회원가입한다.
2. 해당 사용자로 로그인하고 가상계좌를 생성한다.
3. `GET /api/v1/auth/me`와 `GET /api/v1/accounts/me`가 사용자와 계좌를 반환하는지 확인한다.
4. Backend를 재시작한다.

```bash
docker compose restart backend
curl --fail http://localhost:8000/health/dependencies
```

5. 같은 사용자로 다시 로그인해 데이터가 유지되는지 확인한다.
6. 다른 PC에서도 같은 Azure `DATABASE_URL`과 동일한 공용 개발용 `JWT_SECRET`을 설정해 같은 계정/계좌가 조회되는지 확인한다.

JWT는 각 Backend가 토큰을 동일하게 검증하도록 팀 공용 환경에서 같은 `JWT_SECRET`을 사용한다. 비밀번호는 회원가입 API의 기존 `hash_password()`로 해시되며 평문으로 DB에 저장되지 않는다.

별도 개발용 사용자 자동 seed는 만들지 않는다. 필요한 공용 계정은 회원가입 API로 한 번 생성한다.

## 테스트 정책

공용 Azure DB는 팀의 개발·시연 데이터를 담으므로 테스트가 전체 데이터를 초기화하거나 임의로 삭제하면 안 된다.

현재 통합 테스트처럼 테스트 전용 사용자를 생성하고 자신이 만든 데이터만 정리하는 테스트는 공용 DB에서 실행할 수 있다.

```bash
docker compose exec -T backend env RUN_INTEGRATION=1 pytest -q tests/test_integration_flow.py
```

다음과 같은 파괴적 테스트가 필요하면 공용 Azure DB가 아닌 별도 임시 PostgreSQL을 사용한다.

- 전체 schema drop/recreate
- DB 전체 truncate
- migration rollback 실험
- 대량 fixture 초기화
- 장애 복구/복원 실험

이 임시 DB는 테스트 실행 범위에만 존재하며 일반 `docker compose up` 개발 경로에는 포함하지 않는다.

## Azure에서 직접 해야 하는 작업

코드는 Azure 리소스나 Firewall을 생성하지 않는다. 팀 관리자가 Portal 또는 Azure CLI로 다음을 수행한다.

1. 구독과 비용 정책에 맞는 Resource Group, Region, SKU를 선택한다.
2. Azure Database for PostgreSQL Flexible Server를 생성한다.
3. 프로젝트 DB와 최소 권한 애플리케이션 사용자를 만든다.
4. Public Access가 필요하면 개발자들의 현재 공인 IP만 Firewall allowlist에 추가한다.
5. 서버 FQDN, DB 이름, 사용자명, 비밀번호로 `sslmode=require` URL을 작성한다.
6. 각 개발자의 `.env`에 URL과 공용 `JWT_SECRET`을 안전하게 배포한다.
7. `develop` 기준 `db-init`, dependency health, 회원가입/로그인 검증을 수행한다.

Portal에서는 Flexible Server의 **Networking**에서 Public access와 Firewall rules를, **Overview**에서 Server name을 확인한다.

참고 Azure CLI:

```bash
az login
az account set --subscription <SUBSCRIPTION_ID>

az postgres flexible-server show \
  --resource-group <RESOURCE_GROUP> \
  --name <SERVER_NAME> \
  --query '{host:fullyQualifiedDomainName,admin:administratorLogin,publicAccess:network.publicNetworkAccess}' \
  --output table

az postgres flexible-server firewall-rule create \
  --resource-group <RESOURCE_GROUP> \
  --name <SERVER_NAME> \
  --rule-name <DEVELOPER_NAME> \
  --start-ip-address <DEVELOPER_PUBLIC_IP> \
  --end-ip-address <DEVELOPER_PUBLIC_IP>
```

CLI 인자에 비밀번호를 직접 넣으면 shell history나 프로세스 목록에 노출될 수 있으므로 Portal의 보안 입력 또는 팀의 Secret 관리 절차를 우선한다.

## 장애 확인

### `DATABASE_URL is required`

`.env`에 Azure PostgreSQL `DATABASE_URL`이 없거나 빈 값이다. 팀 공용 URL을 설정한 뒤 컨테이너를 다시 생성한다.

```bash
docker compose up -d --build --force-recreate
```

### DB timeout

Azure Public Access, 현재 공인 IP Firewall 규칙, 로컬 outbound TCP 5432를 확인한다.

### TLS 오류

URL 끝의 `sslmode=require`를 확인한다.

### `TERMS_CATALOG_UNAVAILABLE`

`db-init` 성공 여부와 `SIGNUP_TERMS_EFFECTIVE_AT`이 현재보다 미래인지 확인한다.

### 로그인했는데 사용자가 없음

먼저 Backend의 실제 DB host를 확인한다. 팀 공용 Azure DB에 해당 계정이 생성된 적이 없다면 회원가입 API로 한 번 생성한다.

### Secret 노출

URL이나 비밀번호가 노출되었다면 즉시 credential을 회전하고 Git history 및 공유 로그에서 제거한다.
