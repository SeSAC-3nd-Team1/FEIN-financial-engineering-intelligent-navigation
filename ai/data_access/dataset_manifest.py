"""Validation and reproducibility manifests for versioned feature datasets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from models.contracts import DEFAULT_FEATURE_COLUMNS

KEY_COLUMNS = ("trade_date", "stock_code")
TARGET_HORIZONS = (5, 20)
SPLIT_VALUES = ("train", "validation", "test")


class DatasetValidationError(ValueError):
    """Raised with all detected contract violations before model training."""

    def __init__(self, issues: Sequence[str]) -> None:
        self.issues = tuple(issues)
        super().__init__("feature dataset validation failed: " + "; ".join(self.issues))


@dataclass(frozen=True)
class FeatureFile:
    """Immutable identity fields for one Azure Parquet object."""

    path: str
    size: int
    etag: str
    last_modified: str | None = None

    def __post_init__(self) -> None:
        if not self.path.endswith(".parquet") or self.path.startswith("/"):
            raise ValueError("feature file path must be a relative Parquet path")
        if self.size <= 0:
            raise ValueError("feature file size must be positive")
        if not self.etag:
            raise ValueError("feature file ETag is required for reproducible reads")


@dataclass(frozen=True)
class DatasetContract:
    """Columns and quality rules required by a training dataset."""

    key_columns: tuple[str, ...] = KEY_COLUMNS
    feature_columns: tuple[str, ...] = DEFAULT_FEATURE_COLUMNS
    target_horizons: tuple[int, ...] = TARGET_HORIZONS
    split_column: str = "split"
    warmup_column: str = "history_120d_ready"
    warmup_reference_column: str = "momentum_120d"
    max_feature_missing_rate: float = 0.25
    max_target_missing_rate: float = 0.25

    def __post_init__(self) -> None:
        if not self.key_columns or len(set(self.key_columns)) != len(self.key_columns):
            raise ValueError("key_columns must be non-empty and unique")
        if not self.feature_columns or len(set(self.feature_columns)) != len(self.feature_columns):
            raise ValueError("feature_columns must be non-empty and unique")
        if not self.target_horizons or any(value <= 0 for value in self.target_horizons):
            raise ValueError("target_horizons must contain positive values")
        if not self.warmup_reference_column:
            raise ValueError("warmup_reference_column is required")
        for value in (self.max_feature_missing_rate, self.max_target_missing_rate):
            if not 0 <= value <= 1:
                raise ValueError("missing-rate limits must be in [0, 1]")

    @property
    def target_columns(self) -> tuple[str, ...]:
        return tuple(f"target_return_{horizon}d" for horizon in self.target_horizons)

    @property
    def target_date_columns(self) -> tuple[str, ...]:
        return tuple(f"target_date_{horizon}d" for horizon in self.target_horizons)

    @property
    def eligible_columns(self) -> tuple[str, ...]:
        return tuple(f"eligible_target_{horizon}d" for horizon in self.target_horizons)

    @property
    def required_columns(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                (
                    *self.key_columns,
                    *self.feature_columns,
                    *self.target_columns,
                    *self.target_date_columns,
                    *self.eligible_columns,
                    self.split_column,
                    self.warmup_column,
                    self.warmup_reference_column,
                )
            )
        )


@dataclass(frozen=True)
class DatasetValidationReport:
    """Serializable quality summary emitted only for a valid dataset."""

    row_count: int
    security_count: int
    min_trade_date: str
    max_trade_date: str
    duplicate_key_count: int
    warmup_row_count: int
    feature_missing_rates: dict[str, float]
    target_missing_rates: dict[str, float]
    eligible_target_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrainingDatasetManifest:
    """Reproducible identity and validation report for one training input."""

    manifest_version: int
    dataset: str
    version: str
    generated_at: str
    manifest_id: str
    schema_fingerprint: str
    files: tuple[FeatureFile, ...]
    report: DatasetValidationReport

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)


def schema_descriptor(frame: pd.DataFrame) -> tuple[tuple[str, str], ...]:
    """Return an ordered, stable pandas schema representation."""

    return tuple((str(column), str(dtype)) for column, dtype in frame.dtypes.items())


def schema_fingerprint(frame: pd.DataFrame) -> str:
    payload = json.dumps(schema_descriptor(frame), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_partition_schemas(frames: Sequence[pd.DataFrame]) -> str:
    if not frames:
        raise DatasetValidationError(["dataset has no Parquet partitions"])
    expected = schema_descriptor(frames[0])
    mismatches = [
        index
        for index, frame in enumerate(frames[1:], start=1)
        if schema_descriptor(frame) != expected
    ]
    if mismatches:
        raise DatasetValidationError([f"partition schema mismatch at indexes: {mismatches}"])
    return schema_fingerprint(frames[0])


def _missing_rates(frame: pd.DataFrame, columns: Iterable[str]) -> dict[str, float]:
    return {column: float(frame[column].isna().mean()) for column in columns}


def _validate_numeric_finite(
    frame: pd.DataFrame,
    columns: Iterable[str],
    issues: list[str],
) -> None:
    for column in columns:
        numeric = pd.to_numeric(frame[column], errors="coerce")
        original_non_null = frame[column].notna()
        if numeric[original_non_null].isna().any():
            issues.append(f"{column} contains non-numeric values")
        finite_values = numeric.dropna().to_numpy(dtype=float)
        if finite_values.size and not np.isfinite(finite_values).all():
            issues.append(f"{column} contains infinite values")


def _validate_chronological_split(
    data: pd.DataFrame,
    trade_dates: pd.Series,
    split_column: str,
    issues: list[str],
) -> None:
    observed = set(data[split_column].dropna().astype(str).unique())
    missing_splits = [split for split in SPLIT_VALUES if split not in observed]
    if missing_splits:
        issues.append(f"split is missing required values: {missing_splits}")

    if trade_dates.isna().any():
        return
    dates = pd.Index(sorted(trade_dates.unique()))
    if len(dates) < 3:
        issues.append("split requires at least 3 unique trade dates")
        return

    train_index = int(len(dates) * 0.70) - 1
    validation_index = int(len(dates) * 0.85) - 1
    if (
        train_index < 0
        or validation_index <= train_index
        or validation_index >= len(dates) - 1
    ):
        issues.append("split cannot satisfy chronological 70/15/15 boundaries")
        return

    train_end = pd.Timestamp(dates[train_index])
    validation_end = pd.Timestamp(dates[validation_index])
    expected = pd.Series("test", index=data.index, dtype="string")
    expected.loc[trade_dates.le(train_end)] = "train"
    expected.loc[trade_dates.gt(train_end) & trade_dates.le(validation_end)] = "validation"
    actual = data[split_column].astype("string")
    mismatch = actual.notna() & actual.ne(expected)
    if mismatch.any():
        issues.append(
            "split is inconsistent with chronological 70/15/15 contract: "
            f"{int(mismatch.sum())} rows"
        )


def validate_feature_dataset(
    frame: pd.DataFrame,
    contract: DatasetContract = DatasetContract(),
) -> DatasetValidationReport:
    """Validate a complete point-in-time stock panel before model training."""

    issues: list[str] = []
    if frame.empty:
        raise DatasetValidationError(["dataset cannot be empty"])

    missing = sorted(set(contract.required_columns) - set(frame.columns))
    if missing:
        raise DatasetValidationError([f"required columns missing: {missing}"])

    data = frame.copy()
    for column in contract.key_columns:
        if data[column].isna().any():
            issues.append(f"key column {column} contains null values")
    duplicate_count = int(data.duplicated(list(contract.key_columns)).sum())
    if duplicate_count:
        issues.append(f"duplicate key rows: {duplicate_count}")

    trade_dates = pd.to_datetime(data["trade_date"], errors="coerce")
    if trade_dates.isna().any():
        issues.append("trade_date contains invalid values")
    stock_codes = data["stock_code"].astype("string")
    if stock_codes.str.strip().eq("").fillna(False).any():
        issues.append("stock_code contains empty values")

    split_values = set(data[contract.split_column].dropna().astype(str).unique())
    invalid_splits = sorted(split_values - set(SPLIT_VALUES))
    if data[contract.split_column].isna().any() or invalid_splits:
        issues.append(f"split contains invalid values: {invalid_splits}")
    _validate_chronological_split(data, trade_dates, contract.split_column, issues)

    numeric_columns = tuple(
        dict.fromkeys(
            (
                *contract.feature_columns,
                *contract.target_columns,
                contract.warmup_reference_column,
            )
        )
    )
    _validate_numeric_finite(data, numeric_columns, issues)
    feature_missing = _missing_rates(data, contract.feature_columns)
    target_missing = _missing_rates(data, contract.target_columns)
    excessive_features = sorted(
        column for column, rate in feature_missing.items() if rate > contract.max_feature_missing_rate
    )
    if excessive_features:
        issues.append(f"feature missing-rate limit exceeded: {excessive_features}")
    excessive_targets = sorted(
        column for column, rate in target_missing.items() if rate > contract.max_target_missing_rate
    )
    if excessive_targets:
        issues.append(f"target missing-rate limit exceeded: {excessive_targets}")

    boolean_columns = (contract.warmup_column, *contract.eligible_columns)
    invalid_boolean_columns = [
        column for column in boolean_columns if not pd.api.types.is_bool_dtype(data[column].dtype)
    ]
    if invalid_boolean_columns:
        issues.append(f"boolean contract columns have invalid dtype: {invalid_boolean_columns}")
    null_boolean_columns = [column for column in boolean_columns if data[column].isna().any()]
    if null_boolean_columns:
        issues.append(f"boolean contract columns contain null values: {null_boolean_columns}")

    warmup = data[contract.warmup_column].fillna(False).astype(bool)
    expected_warmup = data[contract.warmup_reference_column].notna()
    inconsistent_warmup = warmup.ne(expected_warmup)
    if inconsistent_warmup.any():
        issues.append(
            f"{contract.warmup_column} is inconsistent with "
            f"{contract.warmup_reference_column} availability: "
            f"{int(inconsistent_warmup.sum())} rows"
        )
    ready_missing = data.loc[warmup, list(contract.feature_columns)].isna().any(axis=1)
    if ready_missing.any():
        issues.append(f"warm-up ready rows contain missing features: {int(ready_missing.sum())}")

    eligible_counts: dict[str, int] = {}
    split_ends = trade_dates.groupby(data[contract.split_column]).max()
    for horizon in contract.target_horizons:
        target_column = f"target_return_{horizon}d"
        date_column = f"target_date_{horizon}d"
        eligible_column = f"eligible_target_{horizon}d"
        target_dates = pd.to_datetime(data[date_column], errors="coerce", format="mixed")
        invalid_target_dates = data[date_column].notna() & target_dates.isna()
        if invalid_target_dates.any():
            issues.append(f"{date_column} contains invalid values")
        eligible = data[eligible_column].fillna(False).astype(bool)
        eligible_counts[eligible_column] = int(eligible.sum())

        invalid_observation = (
            target_dates.notna()
            & trade_dates.notna()
            & target_dates.le(trade_dates)
        )
        if invalid_observation.any():
            issues.append(f"{date_column} must be later than trade_date")
        incomplete = eligible & (target_dates.isna() | data[target_column].isna())
        if incomplete.any():
            issues.append(f"{eligible_column} rows require target value and observation date")
        row_split_ends = data[contract.split_column].map(split_ends)
        expected_eligible = (
            target_dates.notna()
            & data[target_column].notna()
            & target_dates.le(row_split_ends)
        )
        inconsistent = eligible.ne(expected_eligible)
        if inconsistent.any():
            issues.append(
                f"{eligible_column} is inconsistent with target availability and split boundary: "
                f"{int(inconsistent.sum())} rows"
            )
        for split, split_end in split_ends.items():
            crosses_boundary = (
                eligible
                & data[contract.split_column].eq(split)
                & target_dates.gt(split_end)
            )
            if crosses_boundary.any():
                issues.append(f"{eligible_column} crosses {split} split boundary")

    if issues:
        raise DatasetValidationError(issues)

    return DatasetValidationReport(
        row_count=len(data),
        security_count=int(stock_codes.nunique()),
        min_trade_date=trade_dates.min().date().isoformat(),
        max_trade_date=trade_dates.max().date().isoformat(),
        duplicate_key_count=duplicate_count,
        warmup_row_count=int((~warmup).sum()),
        feature_missing_rates=feature_missing,
        target_missing_rates=target_missing,
        eligible_target_counts=eligible_counts,
    )


def build_training_manifest(
    *,
    dataset: str,
    version: str,
    files: Sequence[FeatureFile],
    frames: Sequence[pd.DataFrame],
    contract: DatasetContract = DatasetContract(),
    generated_at: datetime | None = None,
) -> TrainingDatasetManifest:
    """Validate partitions and build a content-identifying training manifest."""

    if not files or len(files) != len(frames):
        raise DatasetValidationError(["file identities must match Parquet partitions"])
    if len({file.path for file in files}) != len(files):
        raise DatasetValidationError(["feature file paths must be unique"])
    partitions = tuple(
        sorted(zip(files, frames, strict=True), key=lambda item: item[0].path)
    )
    normalized_files = tuple(file for file, _ in partitions)
    normalized_frames = tuple(frame for _, frame in partitions)
    fingerprint = validate_partition_schemas(normalized_frames)
    report = validate_feature_dataset(pd.concat(normalized_frames, ignore_index=True), contract)
    normalized_version = version.removeprefix("v")
    identity = {
        "manifest_version": 1,
        "dataset": dataset,
        "version": normalized_version,
        "schema_fingerprint": fingerprint,
        "files": [asdict(file) for file in normalized_files],
        "report": report.to_dict(),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    manifest_id = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    timestamp = generated_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    return TrainingDatasetManifest(
        generated_at=timestamp.astimezone(timezone.utc).isoformat(),
        manifest_id=manifest_id,
        files=normalized_files,
        report=report,
        **{
            key: identity[key]
            for key in ("manifest_version", "dataset", "version", "schema_fingerprint")
        },
    )
