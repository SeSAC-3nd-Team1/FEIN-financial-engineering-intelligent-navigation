from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd
import pytest

from data_access.dataset_manifest import (
    DatasetContract,
    DatasetValidationError,
    FeatureFile,
    build_training_manifest,
    validate_feature_dataset,
)


CONTRACT = DatasetContract(
    feature_columns=("signal",),
    target_horizons=(5,),
    max_feature_missing_rate=0.25,
    max_target_missing_rate=0.25,
)


def valid_frame() -> pd.DataFrame:
    dates = pd.to_datetime(["2026-01-02", "2026-01-03", "2026-02-02", "2026-02-03"])
    return pd.DataFrame(
        {
            "trade_date": dates,
            "stock_code": ["A", "B", "A", "B"],
            "signal": [1.0, 2.0, 3.0, 4.0],
            "momentum_120d": [0.1, 0.2, 0.3, 0.4],
            "target_return_5d": [0.01, -0.01, 0.02, 0.03],
            "target_date_5d": dates + pd.Timedelta(days=1),
            "eligible_target_5d": pd.Series([True, False, False, False], dtype="bool"),
            "split": ["train", "train", "validation", "test"],
            "history_120d_ready": pd.Series([True, True, True, True], dtype="bool"),
        }
    )


def test_valid_dataset_report_contains_quality_summary() -> None:
    report = validate_feature_dataset(valid_frame(), CONTRACT)

    assert report.row_count == 4
    assert report.security_count == 2
    assert report.min_trade_date == "2026-01-02"
    assert report.max_trade_date == "2026-02-03"
    assert report.feature_missing_rates == {"signal": 0.0}
    assert report.eligible_target_counts == {"eligible_target_5d": 1}


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True), "duplicate key"),
        (lambda frame: frame.assign(signal=[1.0, np.inf, 3.0, 4.0]), "infinite"),
        (lambda frame: frame.assign(signal=[np.nan, np.nan, 3.0, 4.0]), "missing-rate"),
        (
            lambda frame: frame.assign(
                signal=[np.nan, 2.0, 3.0, 4.0],
                history_120d_ready=pd.Series([True] * 4, dtype="bool"),
            ),
            "warm-up ready",
        ),
        (
            lambda frame: frame.assign(
                target_date_5d=["invalid", "2026-01-04", "2026-02-03", "2026-02-04"]
            ),
            "contains invalid values",
        ),
        (
            lambda frame: frame.assign(
                target_date_5d=pd.to_datetime(
                    ["2026-01-02", "2026-01-04", "2026-02-03", "2026-02-04"]
                )
            ),
            "later than trade_date",
        ),
        (
            lambda frame: frame.assign(
                target_date_5d=pd.to_datetime(
                    ["2026-01-04", "2026-01-04", "2026-02-03", "2026-02-04"]
                )
            ),
            "crosses train split boundary",
        ),
        (
            lambda frame: frame.assign(
                eligible_target_5d=pd.Series([False, False, False, False], dtype="bool")
            ),
            "is inconsistent",
        ),
    ],
)
def test_invalid_dataset_is_blocked_before_training(mutate, message: str) -> None:
    with pytest.raises(DatasetValidationError, match=message):
        validate_feature_dataset(mutate(valid_frame()), CONTRACT)


def test_boolean_contract_columns_require_boolean_dtype() -> None:
    frame = valid_frame()
    frame["eligible_target_5d"] = ["false", "false", "false", "false"]

    with pytest.raises(DatasetValidationError, match="boolean contract"):
        validate_feature_dataset(frame, CONTRACT)


def test_split_requires_train_validation_and_test() -> None:
    frame = valid_frame()
    frame["split"] = ["train", "train", "validation", "validation"]

    with pytest.raises(DatasetValidationError, match="missing required values"):
        validate_feature_dataset(frame, CONTRACT)


def test_split_must_match_chronological_70_15_15_assignment() -> None:
    frame = valid_frame()
    frame["split"] = ["train", "validation", "train", "test"]

    with pytest.raises(DatasetValidationError, match="chronological 70/15/15 contract"):
        validate_feature_dataset(frame, CONTRACT)


def test_warmup_flag_must_match_momentum_120d_availability() -> None:
    frame = valid_frame()
    frame["history_120d_ready"] = pd.Series([False] * 4, dtype="bool")

    with pytest.raises(DatasetValidationError, match="momentum_120d availability"):
        validate_feature_dataset(frame, CONTRACT)


def test_boolean_contract_columns_reject_nulls() -> None:
    frame = valid_frame()
    frame["history_120d_ready"] = pd.Series(
        [True, pd.NA, True, True], dtype="boolean"
    )

    with pytest.raises(DatasetValidationError, match="contain null values"):
        validate_feature_dataset(frame, CONTRACT)


def test_eligible_target_columns_reject_nulls() -> None:
    frame = valid_frame()
    frame["eligible_target_5d"] = pd.Series(
        [True, pd.NA, False, False], dtype="boolean"
    )

    with pytest.raises(DatasetValidationError, match="contain null values"):
        validate_feature_dataset(frame, CONTRACT)


def test_manifest_is_reproducible_and_json_serializable() -> None:
    frame = valid_frame()
    files = (
        FeatureFile(
            path="model_stock_daily/version=v2/year=2026/month=01/part.parquet",
            size=123,
            etag="etag-1",
            last_modified="2026-03-01T00:00:00+00:00",
        ),
    )
    first = build_training_manifest(
        dataset="model_stock_daily",
        version="v2",
        files=files,
        frames=(frame,),
        contract=CONTRACT,
        generated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    second = build_training_manifest(
        dataset="model_stock_daily",
        version="2",
        files=files,
        frames=(frame.copy(),),
        contract=CONTRACT,
        generated_at=datetime(2026, 3, 2, tzinfo=timezone.utc),
    )

    assert first.manifest_id == second.manifest_id
    assert first.generated_at != second.generated_at
    payload = json.loads(first.to_json())
    assert payload["schema_fingerprint"] == first.schema_fingerprint
    assert payload["files"][0]["etag"] == "etag-1"


def test_manifest_identity_is_independent_of_partition_argument_order() -> None:
    frame = valid_frame()
    january = frame.iloc[:2].copy()
    february = frame.iloc[2:].copy()
    january_file = FeatureFile(
        "model_stock_daily/version=v2/year=2026/month=01/part.parquet",
        10,
        etag="etag-jan",
    )
    february_file = FeatureFile(
        "model_stock_daily/version=v2/year=2026/month=02/part.parquet",
        20,
        etag="etag-feb",
    )

    ordered = build_training_manifest(
        dataset="model_stock_daily",
        version="2",
        files=(january_file, february_file),
        frames=(january, february),
        contract=CONTRACT,
    )
    reversed_order = build_training_manifest(
        dataset="model_stock_daily",
        version="2",
        files=(february_file, january_file),
        frames=(february, january),
        contract=CONTRACT,
    )

    assert ordered.manifest_id == reversed_order.manifest_id
    assert tuple(file.path for file in reversed_order.files) == (
        january_file.path,
        february_file.path,
    )


def test_manifest_rejects_duplicate_file_paths() -> None:
    file = FeatureFile("model_stock_daily/version=v2/part.parquet", 1, etag="etag")

    with pytest.raises(DatasetValidationError, match="paths must be unique"):
        build_training_manifest(
            dataset="model_stock_daily",
            version="2",
            files=(file, file),
            frames=(valid_frame().iloc[:2], valid_frame().iloc[2:]),
            contract=CONTRACT,
        )


def test_partition_schema_mismatch_is_rejected() -> None:
    first = valid_frame().iloc[:2].copy()
    second = valid_frame().iloc[2:].copy()
    second["signal"] = second["signal"].astype("int64")
    files = (
        FeatureFile("model_stock_daily/version=v2/a.parquet", 1, etag="etag-a"),
        FeatureFile("model_stock_daily/version=v2/b.parquet", 1, etag="etag-b"),
    )

    with pytest.raises(DatasetValidationError, match="schema mismatch"):
        build_training_manifest(
            dataset="model_stock_daily",
            version="2",
            files=files,
            frames=(first, second),
            contract=CONTRACT,
        )
