from __future__ import annotations

import json

from processing.processed_builder import build_processed_dataset, processed_path, quality_path
from processing.raw_reader import RawBlob
from scripts.audit_model_data_outputs import render_audit_markdown
from scripts.run_financial_pipeline import _render_profile_index, _safe_version


class ResumeStorage:
    def __init__(self, manifest_path: str, output_path: str, manifest: dict):
        self.manifest_path = manifest_path
        self.output_path = output_path
        self.manifest = manifest

    def exists(self, container: str, path: str) -> bool:
        return path in {self.manifest_path, self.output_path}

    def download_bytes(self, container: str, path: str) -> bytes:
        assert path == self.manifest_path
        return json.dumps(self.manifest).encode()


def test_processed_resume_skips_completed_month(monkeypatch):
    dataset = "stock_price"
    operation = "getstockpriceinfo"
    year = 2026
    month = 8
    schema_version = "1"
    output = processed_path(dataset, operation, year, month, schema_version)
    manifest_path = quality_path(dataset, operation, year, month, schema_version)
    manifest = {
        "dataset": dataset,
        "operation": operation,
        "year": year,
        "month": month,
        "schema_version": schema_version,
        "output_path": output,
        "accepted": 123,
        "rejected": 2,
        "conversion_errors": {"close_price": 1},
    }
    storage = ResumeStorage(manifest_path, output, manifest)
    blob = RawBlob(
        path="data-go-kr/stock_price/operation=getstockpriceinfo/year=2026/month=08/"
        + "a" * 64
        + ".jsonl.gz",
        dataset=dataset,
        operation=operation,
        year=year,
        month=month,
        size=100,
    )

    monkeypatch.setattr(
        "processing.processed_builder.list_raw_blobs",
        lambda *_args, **_kwargs: [blob],
    )
    monkeypatch.setattr(
        "processing.processed_builder.read_blob_records",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("completed partition must not read Raw payload")
        ),
    )

    summary = build_processed_dataset(
        storage,
        raw_container="raw",
        processed_container="processed",
        dataset=dataset,
        profile={"operations": {operation: {}}},
        schema_version=schema_version,
        overwrite=False,
    )

    assert summary["files"] == 1
    assert summary["accepted"] == 123
    assert summary["rejected"] == 2
    assert summary["conversion_errors"] == {"close_price": 1}


def test_profile_index_is_human_readable():
    markdown = _render_profile_index(
        [
            {
                "dataset": "stock_price",
                "total_blobs": 2,
                "total_rows": 100,
                "compressed_bytes": 200,
                "operations": {"getstockpriceinfo": {}},
            }
        ]
    )
    assert "Raw Profile Index" in markdown
    assert "stock_price" in markdown
    assert "100" in markdown


def test_audit_markdown_includes_modeling_safety():
    payload = {
        "processed": {
            "total_objects": 1,
            "total_records": 100,
            "total_bytes": 1000,
            "datasets": {
                "stock_price": {"objects": 1, "records": 100, "bytes": 1000}
            },
            "quality": {
                "manifests": 1,
                "accepted": 100,
                "rejected": 0,
                "conversion_errors": {},
                "reasons": {},
            },
        },
        "features": {
            "total_objects": 1,
            "total_records": 80,
            "total_bytes": 800,
            "datasets": {
                "model_stock_daily": {"objects": 1, "records": 80, "bytes": 800}
            },
            "manifest_path": "_manifests/model-datasets/version=v1/manifest.json",
            "manifest": {
                "model_stock_daily": {"status": "training_ready"},
                "look_ahead_policy": "do not join unavailable financial data",
            },
        },
    }
    markdown = render_audit_markdown(payload)
    assert "model_stock_daily" in markdown
    assert "training_ready" in markdown
    assert "look-ahead policy" in markdown


def test_pipeline_version_rejects_path_segments():
    assert _safe_version("1.0") == "1.0"
    try:
        _safe_version("../1")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe version must be rejected")
