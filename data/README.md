# Data

데이터 수집, Raw Blob 저장, PostgreSQL 모델/마이그레이션, Parquet 변환과 Feature 생성을 담당한다.

## 현재 원칙

- API Raw 원문 source of truth: Azure Blob Storage
- PostgreSQL: 현재 회원가입/약관 데이터만 영구 보존
- 금융/API PostgreSQL: 기존 구조 폐기 완료, 8개 Raw dataset 기준으로 재설계 예정
- Raw 원문을 PostgreSQL JSONB에 중복 저장하지 않음
- Azure Storage 인증은 Entra ID/DefaultAzureCredential 우선
- Shared Key 기반 실제 Azure connection string 사용 금지

## 디렉터리

```text
data/
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
