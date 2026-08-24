# Azure PostgreSQL 공용 개발 DB 가이드

이 문서는 서비스 관계형 DB를 Azure Database for PostgreSQL Flexible Server로 공유하는 절차를 설명한다. Azure Blob Storage의 Raw / Processed / Features 데이터와 Redis는 별도 계층이며 변경하지 않는다.

## 연결 모드

Backend, `db-init`, Data, AI는 모두 동일한 `DATABASE_URL` 계약을 사용한다.

| 모드 | `.env`의 `DATABASE_URL` | 실행 명령 |
| --- | --- | --- |
| Local | `postgresql://app:app@postgres:5432/app` | `docker compose up -d --build` |
| Azure | `postgresql://<USER>:<PASSWORD>@<HOST>:5432/<DATABASE>?sslmode=require` | `docker compose up -d --build frontend backend redis` |

기본값은 기존 개발 데이터를 보존하기 위해 Local 모드다. Azure 모드의 명령은 `postgres` 서비스를 요청하지 않으므로 로컬 PostgreSQL 컨테이너 없이 실행된다. `db-init`도 더 이상 `postgres` 서비스에 의존하지 않고 `DATABASE_URL` 대상에 직접 연결한다.

실제 URL은 `.env` 또는 배포 Secret에만 둔다. 비밀번호의 `@`, `:`, `/`, `%`, `#`, `?` 같은 문자는 percent-encoding해야 한다. URL 자체를 채팅, Issue, PR, 로그에 붙이지 않는다.

## 팀원이 새 PC에서 시작하기

```bash
git clone https://github.com/SeSAC-3nd-Team1/SeSAC-3nd-Team1-project.git
cd SeSAC-3nd-Team1-project
git switch develop
cp .env.example .env
```

Local 모드는 `.env`를 그대로 두고 다음을 실행한다.

```bash
docker compose up -d --build
docker compose ps
curl --fail http://localhost:8000/health/dependencies
```

Azure 모드는 팀 관리자가 안전한 채널로 전달한 값을 `.env`의 `DATABASE_URL`에 넣고 다음을 실행한다.

```bash
docker compose up -d --build frontend backend redis
docker compose ps
docker compose logs db-init
curl --fail http://localhost:8000/health/dependencies
```

정상 결과는 `{"postgres":"ok","redis":"ok"}`다. 응답과 초기화 로그는 Connection String이나 driver 원문 오류를 출력하지 않는다.

## Migration과 초기 데이터

수동 적용 명령은 Local/Azure에서 같다.

```bash
docker compose run --rm --no-deps db-init
```

`db-init`은 다음 순서로 동작한다. 개별 연결 제한시간은 `DB_CONNECT_TIMEOUT_SECONDS`로 제한한다.

1. `DATABASE_URL` 연결을 제한적으로 재시도한다.
2. transaction 범위 PostgreSQL advisory lock을 획득한다.
3. 기존 Alembic history에 대해 `upgrade head`를 실행한다.
4. `(term_code, version)` 충돌을 무시하는 약관 seed를 실행한다.
5. 성공하면 commit하고 lock을 해제한다. 실패하면 전체 transaction을 rollback한다.

이미 기록된 Alembic revision은 재적용되지 않으며 기존 약관, 사용자, 가상계좌, 포지션, 주문, 체결, 현금원장을 삭제하거나 덮어쓰지 않는다. `DB_INIT_MAX_ATTEMPTS`와 `DB_INIT_RETRY_SECONDS`는 시작 시 접속 재시도만 조절한다.

현재 schema와 연결 확인:

```bash
docker compose run --rm --no-deps data python -m scripts.check_db
docker compose run --rm --no-deps data alembic current
```

## 회원가입·로그인·영속성 검증

1. `http://localhost:5173`에서 고유한 개발용 사용자 A를 회원가입한다.
2. 사용자 A로 로그인하고 가상계좌를 생성한다.
3. `GET /api/v1/auth/me`와 `GET /api/v1/accounts/me`가 각각 사용자와 계좌를 반환하는지 확인한다.
4. Backend만 재시작한 뒤 같은 사용자로 다시 로그인한다.

```bash
docker compose restart backend
curl --fail http://localhost:8000/health/dependencies
```

5. 다른 PC에서 같은 Azure `DATABASE_URL`과 동일한 `JWT_SECRET`을 설정하고 `frontend backend redis`를 실행한다.
6. 사용자 A로 로그인해 같은 사용자와 가상계좌가 조회되는지 확인한다.

JWT는 각 Backend가 토큰을 동일하게 검증하도록 공용 개발환경에서 같은 `JWT_SECRET`을 사용한다. 비밀번호는 회원가입 API가 기존 `hash_password()`로 해시하므로 평문으로 DB에 저장되지 않는다. 별도 개발용 사용자 seed는 만들지 않는다. 필요한 계정은 회원가입 API로 한 번 생성해 운영환경 자동 계정 생성을 피한다.

자동화된 가입→로그인→`/auth/me`→가상계좌→주문/체결/transaction 회귀 검증은 전용 임시 사용자를 생성하고 자신이 만든 데이터만 정리한다.

```bash
docker compose exec -T backend env RUN_INTEGRATION=1 pytest -q tests/test_integration_flow.py
```

## Azure에서 직접 해야 하는 작업

코드는 Azure 리소스나 Firewall을 생성하지 않는다. 팀 관리자가 Portal 또는 Azure CLI로 다음을 수행해야 한다.

1. 구독과 비용 정책에 맞는 Resource Group, Region, SKU를 선택한다.
2. Azure Database for PostgreSQL Flexible Server를 생성하고 지원되는 PostgreSQL 버전을 선택한다.
3. 공용 개발 전용 DB와 최소 권한 애플리케이션 사용자를 만든다. 일상적인 앱 연결에 관리자 계정을 공유하지 않는 방식을 권장한다.
4. Public Access가 필요하면 개발자들의 현재 공인 IP만 Firewall allowlist에 추가한다. `0.0.0.0` 또는 광범위한 대역은 피한다.
5. 서버 FQDN, DB 이름, 사용자명, 비밀번호로 `sslmode=require` URL을 작성한다.
6. 각 개발자의 `.env`에 URL과 공용 개발용 `JWT_SECRET`을 안전하게 배포한다.
7. `db-init`을 실행하고 `check_db`, dependency health, 회원가입/로그인 검증을 수행한다.

Portal 경로는 Flexible Server의 **Networking**에서 Public access와 Firewall rules를, **Overview**에서 Server name을 확인한다.

다음 Azure CLI 예시는 사용자가 직접 검토해 실행하는 참고 명령이다. 실제 이름, Region, SKU, IP와 Secret을 넣어야 하며 이 저장소는 실행하지 않는다.

```bash
az login
az account set --subscription <SUBSCRIPTION_ID>

az group create \
  --name <RESOURCE_GROUP> \
  --location <REGION>

az postgres flexible-server create \
  --resource-group <RESOURCE_GROUP> \
  --name <SERVER_NAME> \
  --location <REGION> \
  --admin-user <ADMIN_USER> \
  --admin-password '<ADMIN_PASSWORD>' \
  --tier Burstable \
  --sku-name Standard_B1ms \
  --version 17 \
  --public-access <DEVELOPER_PUBLIC_IP>

az postgres flexible-server db create \
  --resource-group <RESOURCE_GROUP> \
  --server-name <SERVER_NAME> \
  --database-name <DATABASE>

az postgres flexible-server firewall-rule create \
  --resource-group <RESOURCE_GROUP> \
  --name <SERVER_NAME> \
  --rule-name <DEVELOPER_NAME> \
  --start-ip-address <DEVELOPER_PUBLIC_IP> \
  --end-ip-address <DEVELOPER_PUBLIC_IP>

az postgres flexible-server show \
  --resource-group <RESOURCE_GROUP> \
  --name <SERVER_NAME> \
  --query '{host:fullyQualifiedDomainName,admin:administratorLogin,publicAccess:network.publicNetworkAccess}' \
  --output table
```

CLI 인자에 비밀번호를 직접 넣으면 shell history나 프로세스 목록에 노출될 수 있으므로 팀의 Secret 관리 절차 또는 Portal의 보안 입력을 우선한다. 서버를 이미 만들었다면 생성 명령을 다시 실행하지 말고 조회·DB 생성·Firewall 명령만 필요한 범위에서 사용한다.

Microsoft 공식 참고 문서:

- [Flexible Server 생성과 연결](https://learn.microsoft.com/azure/postgresql/configure-maintain/quickstart-create-server)
- [Azure CLI Flexible Server 명령](https://learn.microsoft.com/cli/azure/postgres/flexible-server)
- [Firewall 규칙](https://learn.microsoft.com/azure/postgresql/flexible-server/security-firewall-rules)

## 장애 확인

- `db-init`이 재시도 후 실패하면 URL 문법, percent-encoding, DB 이름, 계정 권한을 확인한다.
- timeout이면 Azure Public Access와 현재 공인 IP Firewall 규칙, 로컬 outbound TCP 5432를 확인한다.
- TLS 오류이면 URL 끝의 `sslmode=require`를 확인한다.
- `TERMS_CATALOG_UNAVAILABLE`이면 `db-init` 성공 여부와 `SIGNUP_TERMS_EFFECTIVE_AT`이 현재보다 미래인지 확인한다.
- URL이나 비밀번호가 노출되었다면 즉시 credential을 회전하고 Git history 및 공유 로그에서 제거한다.
