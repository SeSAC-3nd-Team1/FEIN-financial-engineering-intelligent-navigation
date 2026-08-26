"""Algorithm OHLCV Dataset의 전달 계약과 실제 Blob 산출물을 검증한다."""

from __future__ import annotations

import argparse
import io
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from scripts.build_algorithm_dataset import OUTPUT_COLUMNS
from storage import BlobStorage


def validate_frame(frame: pd.DataFrame, path: str) -> dict[str, Any]:
    """한 Parquet의 schema, 자연키, 상태 계약을 검증한다."""

    if list(frame.columns) != OUTPUT_COLUMNS:
        raise RuntimeError(
            f"column contract mismatch path={path} "
            f"expected={OUTPUT_COLUMNS} actual={list(frame.columns)}"
        )
    if frame[["symbol", "Date"]].isna().any(axis=None):
        raise RuntimeError(f"natural key null path={path}")
    duplicate_rows = int(frame.duplicated(["symbol", "Date"], keep=False).sum())
    if duplicate_rows:
        raise RuntimeError(
            f"duplicate symbol and Date path={path} rows={duplicate_rows}"
        )

    expected_status = frame["is_tradable"].map(
        {True: "TRADABLE", False: "NOT_TRADABLE"}
    )
    if not frame["data_status"].equals(expected_status):
        raise RuntimeError(f"data_status mismatch path={path}")
    invalid_reason = frame["is_tradable"] & frame["quality_reason"].ne("")
    missing_reason = (~frame["is_tradable"]) & frame["quality_reason"].eq("")
    if invalid_reason.any() or missing_reason.any():
        raise RuntimeError(f"quality_reason mismatch path={path}")

    reason_counts: Counter[str] = Counter()
    for reasons in frame.loc[~frame["is_tradable"], "quality_reason"]:
        reason_counts.update(reason for reason in str(reasons).split(";") if reason)
    return {
        "rows": len(frame),
        "tradable_rows": int(frame["is_tradable"].sum()),
        "non_tradable_rows": int((~frame["is_tradable"]).sum()),
        "reason_counts": reason_counts,
        "symbols": set(frame["symbol"].astype(str).unique()),
        "min_date": frame["Date"].min(),
        "max_date": frame["Date"].max(),
    }


def validate_dataset(
    storage: BlobStorage,
    *,
    container: str,
    version: str,
) -> dict[str, Any]:
    """Manifest에 선언된 모든 파일을 읽어 Dataset 계약과 집계를 교차검증한다."""

    manifest_path = f"_manifests/algorithm_ohlcv/version=v{version}/manifest.json"
    manifest = json.loads(storage.download_bytes(container, manifest_path))
    if manifest.get("version") != version:
        raise RuntimeError(
            f"manifest version mismatch expected={version} actual={manifest.get('version')}"
        )
    if manifest.get("columns") != OUTPUT_COLUMNS:
        raise RuntimeError("manifest column contract mismatch")
    if version == "2":
        lineage_contract = {
            "direct_source_dataset": "features/model_stock_daily/version=v2/",
            "source_provider": "KRX official API",
            "ohlcv_value_policy": "preserve_direct_source_values_without_imputation",
            "status_columns_origin": "derived_by_data_quality_rules",
            "tradability_semantics": "algorithm_order_eligibility_heuristic",
            "official_trading_halt_status_included": False,
        }
        actual_lineage = {key: manifest.get(key) for key in lineage_contract}
        if actual_lineage != lineage_contract:
            raise RuntimeError(
                "manifest lineage contract mismatch "
                f"expected={lineage_contract} actual={actual_lineage}"
            )

    totals = Counter()
    reasons: Counter[str] = Counter()
    symbols: set[str] = set()
    min_date = None
    max_date = None
    paths = [item["path"] for item in manifest.get("files", [])]
    if not paths:
        raise RuntimeError(f"manifest has no files: {manifest_path}")

    for path in paths:
        frame = pd.read_parquet(io.BytesIO(storage.download_bytes(container, path)))
        result = validate_frame(frame, path)
        totals.update(
            {
                "rows": result["rows"],
                "tradable_rows": result["tradable_rows"],
                "non_tradable_rows": result["non_tradable_rows"],
            }
        )
        reasons.update(result["reason_counts"])
        symbols.update(result["symbols"])
        min_date = (
            result["min_date"]
            if min_date is None
            else min(min_date, result["min_date"])
        )
        max_date = (
            result["max_date"]
            if max_date is None
            else max(max_date, result["max_date"])
        )

    expected = {
        "rows": manifest.get("rows"),
        "tradable_rows": manifest.get("tradable_rows"),
        "non_tradable_rows": manifest.get("non_tradable_rows"),
    }
    actual = {key: totals[key] for key in expected}
    if actual != expected:
        raise RuntimeError(
            f"manifest row counts mismatch expected={expected} actual={actual}"
        )
    if dict(sorted(reasons.items())) != manifest.get("quality_reason_counts"):
        raise RuntimeError("manifest quality reason counts mismatch")
    if len(symbols) != manifest.get("symbols"):
        raise RuntimeError(
            f"manifest symbol count mismatch expected={manifest.get('symbols')} "
            f"actual={len(symbols)}"
        )

    return {
        "dataset": manifest["dataset"],
        "version": version,
        "files": len(paths),
        **actual,
        "symbols": len(symbols),
        "min_date": min_date.date().isoformat(),
        "max_date": max_date.date().isoformat(),
        "quality_reason_counts": dict(sorted(reasons.items())),
    }


def main() -> None:
    """환경변수의 Azure Storage에서 Algorithm Dataset을 읽기 전용 검증한다."""

    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    parser = argparse.ArgumentParser(description="Validate Algorithm OHLCV dataset")
    parser.add_argument("--version", default="2")
    args = parser.parse_args()
    result = validate_dataset(
        BlobStorage.from_env(),
        container=os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features"),
        version=args.version,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
