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

## 2. Raw Blob catalog reconciliation

Azure Blob is authoritative. `raw.data_object` is a searchable PostgreSQL catalog, not a second Raw source of truth.

Read-only Blob audit / DB dry run:

```bash
python scripts/reconcile_raw_blob_catalog.py --expected-minimum 4228
```

Apply catalog reconciliation only from an environment that can reach both Azure Blob and Azure PostgreSQL:

```bash
python scripts/reconcile_raw_blob_catalog.py \
  --apply \
  --expected-minimum 4228
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
python scripts/audit_legacy_raw_table.py
```

Optional exact count is expensive:

```bash
python scripts/audit_legacy_raw_table.py --exact-count
```

A DROP is allowed only after all of the following are confirmed:

1. canonical Raw Blob audit passes;
2. `raw.data_object` reconciliation passes;
3. application/code references have been reviewed;
4. DB foreign-key/view dependencies are zero or explicitly handled;
5. Azure PostgreSQL backup/PITR policy is confirmed;
6. a human explicitly approves the destructive operation.

No automated workflow in this repository drops `raw.public_data_record`.

## 4. Processed Parquet

Processed files are derived from normalized PostgreSQL tables and can be regenerated.

Supported first datasets:

- `stock_price`
- `market_index`

Example:

```bash
python scripts/export_processed_monthly.py \
  --dataset stock_price \
  --start 2021-08-14 \
  --end 2026-08-13 \
  --schema-version 1
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
python scripts/build_stock_price_features.py \
  --start 2021-08-14 \
  --end 2026-08-13 \
  --processed-schema-version 1 \
  --feature-version 1
```

Initial feature set:

- 1-day return
- 1-day log return
- 5-day SMA
- 20-day SMA
- 20-day momentum
- 20-day return volatility
- 20-day volume SMA

A 60-calendar-day warm-up is loaded by default so rolling features at the requested range boundary do not start from an empty history.

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
