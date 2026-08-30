"""정규화된 ECOS 시계열로 point-in-time 거시경제 Feature Dataset을 만든다."""

from __future__ import annotations

import io
import json
import math
import os
from datetime import date, datetime, timezone

import pandas as pd

from collectors.ecos_config import ECOS_SERIES
from storage.paths import build_feature_path


def compute_macro_daily(series_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """관측 당시 가용했던 값만 as-of 결합해 영업일 거시경제 feature를 계산한다."""

    missing = set(ECOS_SERIES) - set(series_frames)
    if missing:
        raise ValueError(f"ECOS processed series missing: {sorted(missing)}")

    prepared: dict[str, pd.DataFrame] = {}
    for name, source in series_frames.items():
        frame = source.copy()
        frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="raise")
        frame["available_at"] = pd.to_datetime(frame["available_at"], errors="raise")
        frame["value"] = pd.to_numeric(frame["value"], errors="raise")
        frame = frame.sort_values(["available_at", "observation_date"])
        if name == "cpi":
            frame["cpi_mom"] = frame["value"].pct_change(fill_method=None)
            frame["cpi_yoy"] = frame["value"].pct_change(12, fill_method=None)
        prepared[name] = frame

    # 환율·채권 실제 거래 관측일의 합집합만 사용해 주말에 인위적인 행을 만들지 않는다.
    trading_dates = sorted(set().union(*(
        set(prepared[name]["observation_date"])
        for name in ("usd_krw", "treasury_3y", "treasury_10y")
    )))
    result = pd.DataFrame({"date": pd.to_datetime(trading_dates)})
    for name, frame in prepared.items():
        columns = ["available_at", "value"]
        if name == "cpi":
            columns += ["cpi_mom", "cpi_yoy"]
        right = frame[columns].drop_duplicates("available_at", keep="last")
        renamed = right.rename(columns={"value": name})
        result = pd.merge_asof(
            result.sort_values("date"), renamed.sort_values("available_at"),
            left_on="date", right_on="available_at", direction="backward",
        ).drop(columns="available_at")

    result["base_rate_change"] = result["base_rate"].diff()
    result["usd_krw_return_1d"] = result["usd_krw"].pct_change(fill_method=None)
    result["usd_krw_return_5d"] = result["usd_krw"].pct_change(5, fill_method=None)
    result["usd_krw_return_20d"] = result["usd_krw"].pct_change(20, fill_method=None)
    result["usd_krw_volatility_20d"] = (
        result["usd_krw_return_1d"].rolling(20, min_periods=20).std() * math.sqrt(252)
    )
    result["treasury_3y_change"] = result["treasury_3y"].diff()
    result["treasury_10y_change"] = result["treasury_10y"].diff()
    result["yield_spread_10y_3y"] = result["treasury_10y"] - result["treasury_3y"]
    return result


def _load_processed(storage, container: str, name: str, schema_version: str) -> pd.DataFrame:
    """한 ECOS Processed 시계열의 모든 월 파티션을 읽는다."""

    prefix = f"ecos/operation={name}/schema=v{schema_version}/"
    frames = [
        pd.read_parquet(io.BytesIO(storage.download_bytes(container, path)))
        for path in storage.list_paths(container, prefix=prefix) if path.endswith(".parquet")
    ]
    if not frames:
        raise RuntimeError(f"ECOS processed series not found: {name}")
    return pd.concat(frames, ignore_index=True)


def build_macro_features(
    storage,
    *,
    processed_container: str,
    features_container: str,
    schema_version: str = "1",
    feature_version: str = "1",
    overwrite: bool = False,
) -> dict[str, object]:
    """ECOS Processed 전체를 macro_daily 월별 Parquet과 manifest로 저장한다."""

    frames = {
        name: _load_processed(storage, processed_container, name, schema_version)
        for name in ECOS_SERIES
    }
    data = compute_macro_daily(frames)
    files: list[str] = []
    for period, monthly in data.groupby(data["date"].dt.to_period("M")):
        path = build_feature_path(
            "macro_daily", version=feature_version,
            partition_date=date(period.year, period.month, 1),
        )
        output = io.BytesIO()
        monthly.to_parquet(output, index=False, compression="zstd")
        storage.upload_bytes(
            features_container, path, output.getvalue(), overwrite=overwrite,
            content_type="application/vnd.apache.parquet",
            metadata={"dataset": "macro_daily", "feature_version": feature_version},
        )
        files.append(path)
    manifest: dict[str, object] = {
        "dataset": "macro_daily", "feature_version": feature_version,
        "processed_schema_version": schema_version, "rows": len(data), "files": files,
        "min_date": data["date"].min().date().isoformat(),
        "max_date": data["date"].max().date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": os.getenv("GIT_SHA", "unknown"),
        "point_in_time_policy": "available_at <= feature date; CPI available from observation month + 2 months",
    }
    storage.upload_bytes(
        features_container, f"_manifests/ecos/version=v{feature_version}/manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
        content_type="application/json", overwrite=True,
    )
    return manifest
