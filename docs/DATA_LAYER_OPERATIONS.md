# Data Layer Operations

## Current architecture

- Azure Blob Storage `raw` is the authoritative, immutable API source layer.
- Canonical Raw path: `data-go-kr/{dataset}/operation={operation}/year=YYYY/month=MM/{hash}.jsonl.gz`.
- Financial/API Raw JSON is not duplicated into PostgreSQL.
- `processed` and `features` are derived Blob layers and may be rebuilt from Raw.
- PostgreSQL currently serves membership/registration relational data, not the financial bulk pipeline.

## Current PostgreSQL state

Current membership/registration tables are defined by Alembic `20260816_0011` and the SQLAlchemy models.

```text
public.users
public.terms
public.user_agreements
public.registration_sessions
public.registration_agreements
public.alembic_version
```

The legacy financial/API PostgreSQL `raw` and `processed` schemas were retired in the `20260816_0010` migration. Historical migrations remain in Alembic history so a database can be reproduced from the beginning; they are not current runtime models.

Apply migrations from the data container:

```bash
docker compose --profile data run --rm --no-deps data alembic upgrade head
```

Check the current database:

```bash
docker compose --profile data run --rm --no-deps data python -m scripts.check_db
```

## Raw collection

The public-data collector writes canonical Raw to Azure Blob and has no financial PostgreSQL dependency.

Example one-day collection:

```bash
docker compose --profile data run --rm --no-deps data python -m scripts.collect_public_data --all-datasets --all-operations --date 2026-08-16 --all-pages --rows 10000
```

Historical collection uses `--start-date` and `--end-date`. `payload.basDt` is the authoritative partition/filter date. Invalid or missing `basDt` aborts the affected operation rather than using another date as fallback.

Five-calendar-year backfill and Raw month-coverage audit:

```bash
docker compose --profile data run --rm --no-deps data python -m scripts.collect_public_data --dataset stock_price --dataset market_index --history-years 5 --all-pages --rows 10000
docker compose --profile data run --rm --no-deps data python -m scripts.audit_raw_coverage --minimum-years 5
```

The coverage audit reads canonical Blob paths only. It proves the span between the first and last
stored month, not completeness of every trading day. The source/priority inventory is maintained in
`data/docs/RAW_DATA_CATALOG.md`.

Daily Raw collection is scheduled by `.github/workflows/raw-daily-collection.yml` at 06:30 UTC
(15:30 KST). It requests each of the previous seven dates independently across all 8 datasets and
52 operations, then verifies the minimum Raw coverage. The workflow requires `DATA_GO_KR_API_KEY`
plus the existing Azure OIDC secrets and Blob write RBAC. GitHub schedules run from the default
branch, so this workflow becomes active after it reaches `main`.

The 2020-01-01 through 2026-08-19 backfill was executed across all 8 datasets and 52 operations.
Core time-series prefixes now span 2020-01 through 2026-08 with no missing month partitions. The
`getStocIssuStat_V3` endpoint required date-sliced backfill because broad range requests timed out;
`scripts.backfill_public_data_by_date` completed the full requested interval with zero final failures.
Snapshot operations such as dividend and item-basic information do not expose daily `basDt` history
and therefore retain only their source-provided snapshot month.

## Financial batch pipeline

The supported bulk path is:

```text
Raw Blob
→ profile
→ validation / normalization
→ Processed Parquet
→ Feature Engineering
→ Features Parquet
→ audit
```

Windows CMD wrapper from repository root:

```cmd
run-financial-pipeline.cmd check
run-financial-pipeline.cmd profile
run-financial-pipeline.cmd processed
run-financial-pipeline.cmd features
run-financial-pipeline.cmd audit
```

Full build:

```cmd
run-financial-pipeline.cmd all
```

Processed uses monthly resume semantics: a partition is skipped only when both Parquet and its quality manifest exist and the manifest contract matches. Use `--overwrite` only for an intentional rebuild.

Raw profiling reports live in:

```text
data/reports/raw-profile/INDEX.md
data/reports/raw-profile/{dataset}.json
data/reports/raw-profile/{dataset}.md
```

The JSON reports are machine-readable profile contracts used by Processed generation; Markdown is the human-readable view. Do not remove the JSON files as documentation duplicates.

## Authentication

Azure Storage uses `AZURE_STORAGE_ACCOUNT_NAME` with `DefaultAzureCredential`/Azure CLI credentials. Shared Key and real Azure connection strings are intentionally rejected. Azurite remains the local-development exception when explicitly configured.

## Historical migration utilities

One-time SQL-Raw migration, repartition, cleanup and destructive retirement entrypoints were removed after completion. Their evidence remains in Git history, issues/PRs and archived reports. Do not reintroduce retired migration scripts into the normal runtime path.

## Modeling safety

- Raw is immutable.
- Numeric-looking identifiers stay strings.
- Missing/empty values are not blindly replaced with zero.
- `security_master_latest` is reference-only and must not reconstruct a historical universe.
- Financial `base_date` is not an availability timestamp; price JOIN remains blocked until actual public disclosure time is known.
- Price targets and rolling windows must be interpreted according to the implementation. Current `shift(N)` logic uses the N-th observed row per security, not an independently reconstructed KRX session calendar.

## Next data work

The next additions should enrich the Blob pipeline rather than recreate the retired financial PostgreSQL landing layer. Examples include OpenDART disclosure availability timestamps, historical KOSPI200 constituents, valuation/corporate-action data, and optional ECOS/customs features.
