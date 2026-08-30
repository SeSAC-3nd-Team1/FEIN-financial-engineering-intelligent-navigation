# 회원가입 PostgreSQL 3NF 구현 가이드

회원가입 데이터의 정식 설계 문서는 다음 두 파일을 기준으로 한다.

- `docs/REGISTRATION_DATA_SPECIFICATION.md`: 컬럼/타입/PK/FK/UNIQUE/CHECK/INDEX와 3NF 근거
- `docs/REGISTRATION_DATA_ERD.md`: PostgreSQL 관계도, Redis 경계, 가입 데이터 흐름

이 문서는 위 설계를 실제 SQLAlchemy/Alembic 코드로 적용하고 검증하는 운영 가이드다.

## 구현된 PostgreSQL 구조

```text
users 1 ---- N user_agreements N ---- 1 terms

registration_sessions 1 ---- N registration_agreements N ---- 1 terms
```

- `users`: 가입 완료 회원. 현재는 이메일 인증이 필수이며 휴대폰 인증 시각은 후속 인증 전까지 `NULL`이다.
- `terms`: 약관 code + version catalog.
- `user_agreements`: 회원과 `term_id` 사이의 약관 동의 감사 이력.
- `registration_sessions`: 가입 완료 전 개인정보/검증 완료 시각을 30분 기본 TTL로 보관한다.
- `registration_agreements`: 가입 세션과 `term_id` 사이의 가입 전 약관 선택 상태.

OTP HMAC digest, attempts, verification token, rate limit은 PostgreSQL에 저장하지 않고 Redis TTL 상태로 관리한다.

## 3NF에서 제거한 중복

- `users.phone_verified` 제거 -> 휴대폰 인증 도입 후 `phone_verified_at IS NOT NULL`로 판정
- `users.email_verified` 제거 -> `email_verified_at IS NOT NULL`로 판정
- `user_agreements.term_code` 제거 -> `term_id -> terms.term_code`
- `user_agreements.term_version` 제거 -> `term_id -> terms.version`
- `user_agreements.is_required` 제거 -> `term_id -> terms.is_required`

따라서 동의 행에는 사용자/약관 관계와 그 관계에 직접 종속되는 감사 속성만 남는다.

## Alembic

3NF 전환 migration은 `20260816_0011`이다.

migration은 기존 데이터를 임의로 보정하거나 삭제하지 않는다.

- 기존 `users` 중 휴대폰/이메일 인증 시각이 없는 행이 있으면 중단한다.
- 기존 `user_agreements`가 `terms.id`에 매핑되지 않으면 중단한다.
- 기존 동의 행은 `term_code + term_version`을 이용해 `term_id`로 backfill한 뒤 정규화한다.

저장소 루트에서 실행한다.

```bash
docker compose --profile data run --rm --no-deps data alembic upgrade head
```

적용 revision 확인:

```bash
docker compose --profile data run --rm --no-deps data alembic current
```

정상 상태는 다음과 같다.

```text
20260816_0011 (head)
```

## 약관 seed

`terms` 구조는 유지되므로 기존 seed script를 그대로 사용한다.

```bash
docker compose --profile data run --rm --no-deps data python -m scripts.seed_signup_terms --version 1 --effective-at 2026-08-14T00:00:00+09:00
```

운영 약관 version/effective_at은 실제 승인값으로 교체한다.

## 실제 PostgreSQL 검증

`verify_signup_schema.py`는 테스트 데이터를 transaction 안에서만 생성하고 마지막에 전부 rollback한다.

검증 범위:

- 5개 목표 테이블 존재
- 주요 UNIQUE/INDEX 존재
- 제거 대상 중복 컬럼 부재
- 정상 users/user_agreements insert
- 회원/약관 중복 및 FK 차단
- 감사 이력이 있는 users/terms 물리 삭제 RESTRICT
- registration session 삭제 시 registration_agreements CASCADE
- 잘못된 user ID 및 duplicate ID/email 차단

실행:

```bash
docker compose --profile data run --rm --no-deps data python -m scripts.verify_signup_schema --term-version 1
```

실제 약관 seed가 없는 개발 DB에서만 임시 약관을 rollback transaction 안에 생성할 수 있다.

```bash
docker compose --profile data run --rm --no-deps data python -m scripts.verify_signup_schema --term-version dev-test --create-temporary-terms
```

## 단위 테스트

```bash
docker compose --profile data run --rm --no-deps data python -m pytest tests -q
```

## 다음 단계

PostgreSQL schema가 검증된 뒤 다음을 별도 이슈로 구현한다.

1. Redis OTP challenge / verification token single-use / rate limit
2. 회원가입 FastAPI endpoint
3. `registration_sessions` -> `users` / `user_agreements` 최종 transaction
4. Redis token consume와 PostgreSQL commit 사이의 실패 복구/idempotency
5. CI/DI Azure Key Vault 암복호화 및 key rotation
