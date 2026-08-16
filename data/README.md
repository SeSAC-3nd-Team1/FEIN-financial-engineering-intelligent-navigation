# Data

데이터 수집, Raw Blob 저장, PostgreSQL 모델/마이그레이션, Parquet 변환과 Feature 생성을 담당한다.

## 현재 원칙

- API Raw 원문 source of truth: Azure Blob Storage
- PostgreSQL: 현재 회원가입/약관 데이터만 영구 보존
- 금융/API PostgreSQL: 기존 구조 폐기 완료, 8개 Raw dataset 기준으로 재설계 예정
- Raw 원문을 PostgreSQL JSONB에 중복 저장하지 않음
- Azure Storage 인증은 Entra ID/DefaultAzureCredential 우선
- Shared Key 기반 실제 Azure connection string 사용 금지

## 코드 주석 규칙

`data/` 영역은 데이터 의미와 운영 제약을 팀원이 빠르게 이해할 수 있도록 한국어 주석과 도큐스트링을 사용한다. 세부 규칙은 `data/AGENTS.md`를 따른다.

- 모듈, 주요 함수, 클래스의 설명은 한국어로 작성
- `basDt` 파티셔닝, hash 기반 멱등성, UPSERT 충돌키, transaction, feature window처럼 실수하기 쉬운 규칙은 왜 필요한지 한국어로 설명
- 단순 대입이나 코드만으로 명확한 부분에는 과도한 주석을 추가하지 않음
- API 필드명, 함수/변수명, SQL 식별자, 환경변수, Azure 서비스명과 로그 키는 기존 영문 유지
- 새 코드 생성이나 기존 코드 수정 시에도 동일한 규칙 적용

## 디렉터리

```text
data/
├─ AGENTS.md         # data 하위 코드 생성/주석 지침
├─ collectors/      # data.go.kr API client/config
├─ db/
│  ├─ connection/   # PostgreSQL 연결
│  ├─ migrations/   # Alembic
│  └─ models/       # 현재 membership 모델
├─ loaders/         # 범용 PostgreSQL UPSERT 유틸
├─ scripts/
│  ├─ collect_public_data.py
│  ├─ audit_raw_partition_dates.py
│  ├─ build_stock_price_features.py
│  ├─ check_db.py
│  ├─ seed_signup_terms.py
│  └─ verify_signup_schema.py
├─ storage/         # Blob auth/path/Raw serialization
├─ transforms/      # Parquet helper
└─ tests/
```

## Raw Blob

Canonical layout:

```text
raw/
└─ data-go-kr/{dataset}/operation={operation}/year=YYYY/month=MM/{sha256}.jsonl.gz
```

`basDt`가 Raw partition의 유일한 기준일이다. `day=DD`, `migration/` prefix, page-number filename은 새 수집 코드에서 지원하지 않는다.

Raw 수집 예시:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.collect_public_data --dataset stock_price --date 2026-08-16 --all-pages --rows 10000
```

## PostgreSQL

현재 보존 대상:

```text
public.users
public.terms
public.user_agreements
public.alembic_version
```

기존 금융/API `raw` 구조는 제거되었다. `20260816_0010` migration이 이 상태를 공식 migration history로 기록한다.

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data alembic upgrade head
```

연결/상태 확인:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.check_db
```

## 테스트

```bash
docker compose --profile data run --rm --no-deps data python -m pytest tests -q
```

## 다음 작업

금융 DB를 만들기 전에 Blob의 8개 dataset(`disclosure`, `financial_statement`, `market_index`, `security_product`, `stock_dividend`, `stock_issuance`, `stock_master`, `stock_price`)의 실제 payload schema를 먼저 profiling한다. 그 결과를 기준으로 새 PostgreSQL 모델과 migration을 설계한다.
