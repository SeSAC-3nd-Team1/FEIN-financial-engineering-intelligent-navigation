# 회원가입 데이터 구조도 (ERD)

> 상태: 목표 설계안(Target Design)
> 기준 이슈: #24
> 상세 컬럼 정의: `docs/REGISTRATION_DATA_SPECIFICATION.md`

## 1. PostgreSQL ERD

```mermaid
erDiagram
    USERS ||--o{ USER_AGREEMENTS : "동의 이력"
    TERMS ||--o{ USER_AGREEMENTS : "약관 version"
    REGISTRATION_SESSIONS ||--o{ REGISTRATION_AGREEMENTS : "가입 전 동의"
    TERMS ||--o{ REGISTRATION_AGREEMENTS : "약관 version"

    USERS {
        bigint id PK
        varchar user_id UK
        varchar password_hash
        varchar name
        char birthdate
        varchar phone_number
        timestamptz phone_verified_at
        varchar email UK
        timestamptz email_verified_at
        bytea ci_encrypted
        bytea ci_lookup_hash UK
        bytea di_encrypted
        varchar telecom_carrier
        varchar gender
        varchar member_type
        varchar account_status
        timestamptz last_login_at
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
    }

    TERMS {
        bigint id PK
        varchar term_code
        varchar version
        varchar title
        varchar content_reference
        boolean is_required
        timestamptz effective_at
        timestamptz created_at
    }

    USER_AGREEMENTS {
        bigint id PK
        bigint user_id FK
        bigint term_id FK
        boolean is_agreed
        timestamptz agreed_at
        inet agreed_ip
        varchar user_agent
    }

    REGISTRATION_SESSIONS {
        uuid id PK
        varchar name
        char birthdate
        varchar phone_number
        timestamptz phone_verified_at
        varchar email
        timestamptz email_verified_at
        timestamptz created_at
        timestamptz expires_at
        timestamptz completed_at
    }

    REGISTRATION_AGREEMENTS {
        uuid registration_id PK,FK
        bigint term_id PK,FK
        boolean is_agreed
        timestamptz agreed_at
        inet agreed_ip
        varchar user_agent
    }
```

## 2. 관계 요약

```text
                           TERMS
                         /       \
                        /         \
                       N           N
                      /             \
                     1               1
       USER_AGREEMENTS          REGISTRATION_AGREEMENTS
              N                         N
              |                         |
              1                         1
            USERS              REGISTRATION_SESSIONS
```

실제 cardinality는 다음과 같다.

- `users 1 : N user_agreements`
- `terms 1 : N user_agreements`
- `registration_sessions 1 : N registration_agreements`
- `terms 1 : N registration_agreements`

`user_agreements`와 `registration_agreements`는 각각 사용자/가입 세션과 약관 version 사이의 교차 관계다.

## 3. Redis를 포함한 전체 데이터 구조

```mermaid
flowchart LR
    FE[Frontend Signup Flow]

    subgraph PG[PostgreSQL]
        RS[registration_sessions]
        RA[registration_agreements]
        U[users]
        UA[user_agreements]
        T[terms]
    end

    subgraph REDIS[Redis]
        OTP[OTP challenge\nTTL 300s]
        VT[verification token state\nTTL 30m]
        RL[rate limit counters]
    end

    FE -->|Step 01| RS
    FE -->|약관 선택| RA
    T --> RA

    FE -->|phone/email send & verify| OTP
    OTP --> VT
    VT -->|검증 결과| RS

    RS -->|최종 signup transaction| U
    RA -->|INSERT SELECT| UA
    T --> UA

    FE --> RL
```

## 4. 가입 완료 시 데이터 전환

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as Backend API
    participant PG as PostgreSQL
    participant R as Redis

    FE->>API: Step 01 개인정보 + 약관
    API->>PG: registration_sessions INSERT
    API->>PG: registration_agreements INSERT
    API->>R: phone OTP challenge SET EX 300

    FE->>API: phone OTP verify
    API->>R: OTP 검증/소비
    API->>PG: phone_verified_at UPDATE
    API->>R: phone verification token state

    FE->>API: email OTP send/verify
    API->>R: email OTP challenge 검증/소비
    API->>PG: email + email_verified_at UPDATE
    API->>R: email verification token state

    FE->>API: POST /users/signup
    API->>R: 두 verification token 검증
    API->>PG: BEGIN
    API->>PG: users INSERT
    API->>PG: registration_agreements -> user_agreements
    API->>PG: registration_sessions.completed_at UPDATE
    API->>PG: COMMIT
    API->>R: token consume 확정
```

## 5. 3NF 관점의 핵심 분리

### 약관 속성은 `terms`에만 존재

```text
terms.id
  -> term_code
  -> version
  -> title
  -> content_reference
  -> is_required
  -> effective_at
```

따라서 `user_agreements`와 `registration_agreements`에는 위 속성을 반복 저장하지 않고 `term_id`만 둔다.

### 인증 여부는 timestamp로 표현

```text
phone_verified_at IS NOT NULL -> 휴대폰 인증 완료
email_verified_at IS NOT NULL -> 이메일 인증 완료
```

별도 `phone_verified`, `email_verified` boolean을 저장하지 않는다.

### 임시 가입 상태와 가입 완료 상태를 분리

```text
registration_sessions / registration_agreements
                  |
                  | signup 성공
                  v
users / user_agreements
```

가입 실패/이탈 데이터가 `users`에 섞이지 않고, 가입 완료 회원 테이블은 실제 계정만 보유한다.

## 6. 삭제 정책

```text
users ---------------------- RESTRICT ---> user_agreements
terms ---------------------- RESTRICT ---> user_agreements
terms ---------------------- RESTRICT ---> registration_agreements
registration_sessions ------ CASCADE ----> registration_agreements
```

- 회원 탈퇴는 `users` physical delete보다 `deleted_at` soft delete를 기본으로 한다.
- 감사용 `user_agreements`는 회원 탈퇴와 함께 자동 삭제하지 않는다.
- 가입 전 임시 세션은 만료/정리 시 `registration_agreements`와 함께 삭제 가능하다.
