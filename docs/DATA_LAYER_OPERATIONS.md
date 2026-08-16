# Data Layer Operations

## 1. Layer contract

| Layer | Storage | Role | Rebuildable |
| --- | --- | --- | --- |
| Raw | Azure Blob `raw` | API payload source of truth | No: preserve source observations |
| Normalized / Service | Azure PostgreSQL | indexed relational queries and service state | Financial normalized data: Yes, from Raw |
| Processed | Azure Blob `processed` | monthly columnar analytics datasets | Yes |
| Features | Azure Blob `features` | versioned ML/model inputs | Yes |
| Temporary | Redis | OTP, verification, cache, short-lived state | Yes |

Raw API records are partitioned by `payload.basDt` month:

```text
data-go-kr/{dataset}/operation={operation}/year=YYYY/month=MM/*.jsonl.gz
```

Other event dates such as `dvdnBasDt`, `stckIssuDt`, `cashDvdnPayDt` are payload fields and do not determine Raw partitions.

Real Azure Blob access uses Entra ID through `DefaultAzureCredential`. `AZURE_STORAGE_ACCOUNT_NAME` takes precedence over any stale connection string. Connection-string authentication is supported only for local Azurite (`UseDevelopmentStorage=true`).

### Docker Azure authentication

The `data` image includes Azure CLI and Compose persists `/root/.azure` in the `azure_cli_data` named volume. This means ephemeral `docker compose run --rm` jobs reuse the same Azure CLI login.

The Azure environment file must include the non-secret storage account name:

```env
AZURE_STORAGE_ACCOUNT_NAME=stfeindata
```

Build the latest data image once after Dockerfile changes:

```bash
docker compose --env-file .env.azure --profile data build data
```

Authenticate from inside the data container:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data az login --use-device-code
```

Verify the persisted login and Storage account environment before running data jobs:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data az account show --output table
docker compose --env-file .env.azure --profile data run --rm --no-deps data sh -lc 'echo $AZURE_STORAGE_ACCOUNT_NAME'
```

Do not enable Azure Storage Shared Key for local development.

## 2. Raw Blob catalog reconciliation

Azure Blob is authoritative. `raw.data_object` is a searchable PostgreSQL catalog, not a second Raw source of truth.

Read-only Blob audit / DB dry run:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.reconcile_raw_blob_catalog --expected-minimum 4228
```

Apply catalog reconciliation only from an environment that can reach both Azure Blob and Azure PostgreSQL:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.reconcile_raw_blob_catalog --apply --expected-minimum 4228
```

Behavior:

- canonical Blob objects are UPSERTed into `raw.data_object`;
- existing catalog rows whose Raw Blob no longer exists are marked `status=deleted`;
- catalog history is not physically deleted;
- Raw Blob payloads are never changed by this command;
- `raw.public_data_migration_manifest` remains as migration audit history.

## 3. Legacy PostgreSQL Raw landing table

`raw.public_data_record` is the historical JSONB landing table used before Azure Blob became the Raw source of truth. It must not be dropped merely because Blob migration completed.

Read-only readiness audit:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.audit_legacy_raw_table
```

Optional exact count is expensive:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.audit_legacy_raw_table --exact-count
```

A DROP is allowed only after all of the following are confirmed:

1. canonical Raw Blob audit passes;
2. `raw.data_object` reconciliation passes;
3. application/code references have been reviewed;
4. DB foreign-key/view dependencies are zero or explicitly handled;
5. Azure PostgreSQL backup/PITR policy is confirmed;
6. a human explicitly approves the destructive operation.

No automated workflow in this repository drops `raw.public_data_record`.

For row retirement after full SQL↔Blob parity verification, use:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.retire_legacy_raw_data --truncate-after-verify --expected-blob-count 4228
```

This command never drops the table. It verifies every canonical Raw object and every historical SQL row before truncating only the duplicated landing rows.

## 4. Processed Parquet

Processed files are derived from normalized PostgreSQL tables and can be regenerated.

Supported first datasets:

- `stock_price`
- `market_index`

Examples:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.export_processed_monthly \
  --dataset stock_price --start 2021-08-14 --end 2026-08-13 --schema-version 1

docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.export_processed_monthly \
  --dataset market_index --start 2021-08-14 --end 2026-08-13 --schema-version 1
```

Output:

```text
processed/
  stock_price/
    schema=v1/
      year=YYYY/
        month=MM/
          part-00000.parquet
```

Existing objects are not overwritten unless `--overwrite` is explicitly supplied.

## 5. Feature Parquet

Feature generation reads Processed Parquet, not Raw Blob or PostgreSQL directly. This keeps feature definitions reproducible and separates storage concerns.

Example:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.build_stock_price_features \
  --start 2021-08-14 --end 2026-08-13 \
  --processed-schema-version 1 --feature-version 1
```

Initial feature set:

- 1-day return
- 1-day log return
- 5-day SMA
- 20-day SMA
- 20-day momentum
- 20-day return volatility
- 20-day volume SMA

A 60-calendar-day warm-up is loaded by default so rolling features at the requested range boundary do not start from an empty history when earlier Processed data exists. At the earliest available Raw/Processed boundary, rolling features remain null until sufficient history accumulates.

Output:

```text
features/
  stock_price/
    version=v1/
      year=YYYY/
        month=MM/
          part-00000.parquet
```

Feature version must change whenever feature definitions, formulas, preprocessing semantics, or leakage policy changes.

## 6. Operational order

```text
External API
  -> Raw Blob
  -> validation / normalization
  -> PostgreSQL
  -> Processed Parquet
  -> Feature Parquet
```

For recovery/reprocessing, always start from Raw Blob. PostgreSQL, Processed, and Features are downstream materializations.

## 7. Guarded financial PostgreSQL reset before rebuild

When rebuilding the financial SQL layer from Blob, membership data must survive unchanged.

Always preserve:

- `public.users`
- `public.terms`
- `public.user_agreements`
- `public.alembic_version`

The guarded command is:

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.rebuild_financial_sql --sync-missing-to-blob --reset-after-sync
```

Before any SQL reset it:

1. snapshots membership table counts;
2. hashes every mapped API-origin normalized `source_payload`;
3. scans the relevant canonical Raw Blob objects and verifies their compressed checksum and payload hashes;
4. identifies API payloads that exist only in SQL;
5. writes only those missing API payloads to canonical monthly Raw Blob;
6. reads newly written objects back and verifies checksum and payload hashes;
7. refuses reset when an unmapped non-null `source_payload` exists;
8. refuses reset when an untouched table has a foreign key into a reset table;
9. uses `TRUNCATE ... RESTART IDENTITY` only on the known financial/raw tables and never uses `CASCADE`;
10. verifies every reset table is empty and membership row counts are unchanged.

Financial/raw reset tables:

- `raw.stock_master`
- `raw.stock_price_daily`
- `raw.market_index_daily`
- `raw.stock_issuance`
- `raw.financial_statement`
- `raw.macro_indicator`
- `raw.public_data_record`
- `raw.public_data_collection_checkpoint`
- `raw.data_object`
- `raw.public_data_migration_manifest`

The current one-row `stock_issuance`, `financial_statement`, and `macro_indicator` records were created by `scripts.load_sample_data`; they are development samples, not API Raw observations.
