"""Blob EDA 요약 로직의 회귀 테스트다."""

from __future__ import annotations

import pytest

from analysis.blob_eda import build_analysis, summarize_profile


def _profile(dataset: str, *, snapshot: bool = False) -> dict:
    first_min = "20260813" if snapshot else "20210817"
    return {
        "dataset": dataset,
        "total_rows": 100,
        "total_blobs": 4,
        "compressed_bytes": 2_000,
        "invalid_paths": [],
        "operations": {
            "main": {
                "rows": 80,
                "malformed_json_lines": 0,
                "invalid_payloads": 0,
                "basdt_missing": 0,
                "basdt_invalid": 0,
                "min_basdt": first_min,
                "max_basdt": "20260813",
                "payload_fields": {
                    "required": {"null_or_empty_rate": 0.0},
                    "sparse": {"null_or_empty_rate": 0.75},
                    "empty": {"null_or_empty_rate": 1.0},
                },
            },
            "secondary": {
                "rows": 20,
                "malformed_json_lines": 0,
                "invalid_payloads": 0,
                "basdt_missing": 0,
                "basdt_invalid": 0,
                "min_basdt": "20260813",
                "max_basdt": "20260813",
                "payload_fields": {},
            },
        },
    }


def test_summarize_profile_detects_mixed_time_axis_and_missing_fields() -> None:
    summary = summarize_profile(_profile("stock_price"))

    assert summary.temporal_shape == "mixed"
    assert summary.high_missing_fields == 1
    assert summary.all_empty_fields == 1
    assert summary.top_operation == "main"
    assert summary.top_operation_share == 0.8
    assert summary.quality_passed is True


def test_snapshot_profile_is_classified_without_false_quality_failure() -> None:
    summary = summarize_profile(_profile("stock_dividend", snapshot=True))

    assert summary.temporal_shape == "snapshot"
    assert summary.min_basdt == "20260813"
    assert summary.max_basdt == "20260813"
    assert summary.invalid_count == 0


def test_build_analysis_aggregates_dataset_totals() -> None:
    analysis = build_analysis(
        [_profile("stock_price"), _profile("stock_dividend", snapshot=True)]
    )

    assert analysis["dataset_count"] == 2
    assert analysis["total_records"] == 200
    assert analysis["total_blobs"] == 8
    assert analysis["total_compressed_bytes"] == 4_000
    assert analysis["quality_passed_datasets"] == 2
    assert analysis["snapshot_datasets"] == ["stock_dividend"]
    assert analysis["mixed_temporal_datasets"] == ["stock_price"]


def test_high_missing_threshold_must_be_valid() -> None:
    with pytest.raises(ValueError):
        summarize_profile(_profile("stock_price"), high_missing_threshold=0.0)
