# Data Layer Operations

## Current architecture

- Azure Blob Storage `raw` is the authoritative, immutable API source layer.
- Canonical Raw path: `data-go-kr/{dataset}/operation={operation}/year=YYYY/month=MM/{hash}.jsonl.gz`.
- PostgreSQL currently persists membership/registration data only.
- Financial/API PostgreSQL schemas were retired and will be redesigned from the eight canonical Raw datasets.
- Processed and Features are derived Blob layers and may be rebuilt.

## PostgreSQL state

Persistent public tables:

- `public.users`
- `public.terms`
- `public.user_agreements`
- `public.alembic_version`

Migration `20260816_0010` formally retires the old `raw` and `processed` PostgreSQL schemas. It is intentionally irreversible; future financial schemas must be created with forward migrations.

Apply migrations from the data container:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data alembic upgrade head
```

Check the current database:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.check_db
```

## Raw collection

The collector writes only to Azure Blob and has no PostgreSQL dependency.

Example one-day collection:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data python -m scripts.collect_public_data --all-datasets --all-operations --date 2026-08-16 --all-pages --rows 10000
```

Historical collection uses `--start-date` and `--end-date`. Payload `basDt` is the sole authoritative partition/filter date. Invalid or missing `basDt` aborts that operation rather than falling back to another date.

## Authentication

Azure Storage uses `AZURE_STORAGE_ACCOUNT_NAME` with `DefaultAzureCredential`. Shared Key and real Azure connection strings are intentionally rejected. Azurite remains the only connection-string exception for local development.

## Historical migration utilities

The SQL-Raw migration, repartition, legacy cleanup, parity verification, and financial reset scripts were removed after successful completion. Their execution evidence remains in Git history, Issue #20, PR history, and the Raw migration report. Production code should not retain one-time destructive migration entrypoints after retirement.

## Next financial data step

Before creating new PostgreSQL financial tables:

1. profile all eight canonical Raw datasets and operations;
2. define relational entities, keys, temporal semantics, and indexes;
3. create new ORM models and a forward Alembic migration;
4. build a Blob-only-to-PostgreSQL loader;
5. validate normalized counts, uniqueness, and date ranges;
6. only then materialize Processed and Features.
