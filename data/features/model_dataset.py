"""Processed 금융 데이터에서 모델 담당자가 바로 사용할 Feature Dataset을 만든다."""

from __future__ import annotations

import io
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def load_processed_operation(
    storage,
    container: str,
    dataset: str,
    operation: str,
    schema_version: str,
) -> pd.DataFrame:
    """한 operation의 월별 Processed Parquet을 하나의 DataFrame으로 읽는다."""

    prefix = f"{dataset}/operation={operation.lower()}/schema=v{schema_version}/"
    frames: list[pd.DataFrame] = []
    client = storage.service_client.get_container_client(container)
    for blob in client.list_blobs(name_starts_with=prefix):
        path = str(blob.name)
        if path.endswith(".parquet"):
            frames.append(pd.read_parquet(io.BytesIO(storage.download_bytes(container, path))))
    if not frames:
        raise RuntimeError(
            f"processed dataset not found: {dataset}/{operation}/schema=v{schema_version}"
        )
    return pd.concat(frames, ignore_index=True)


def _resolve_duplicate_prices(frame: pd.DataFrame) -> pd.DataFrame:
    """동일 종목/거래일 중복은 값이 같을 때만 하나로 축약한다."""

    key = ["stock_code", "trade_date"]
    duplicate_mask = frame.duplicated(key, keep=False)
    if not duplicate_mask.any():
        return frame

    compare_columns = [
        column
        for column in (
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
            "trading_value",
            "market_cap",
        )
        if column in frame
    ]
    conflicts = (
        frame.loc[duplicate_mask]
        .groupby(key, dropna=False)[compare_columns]
        .nunique(dropna=False)
    )
    if not conflicts.empty and (conflicts > 1).any(axis=None):
        raise RuntimeError(
            "conflicting stock price duplicates found for stock_code + trade_date"
        )
    return frame.drop_duplicates(key, keep="first")


def compute_stock_features(frame: pd.DataFrame) -> pd.DataFrame:
    """가격/거래량만으로 재현 가능한 시계열 Feature와 미래 Target을 만든다."""

    required = {"stock_code", "trade_date", "close_price", "volume"}
    missing = required - set(frame)
    if missing:
        raise ValueError(f"stock price processed columns missing: {sorted(missing)}")

    data = frame.copy()
    data["stock_code"] = data["stock_code"].astype("string")
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="raise")
    for column in (
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
        "trading_value",
        "market_cap",
        "listed_shares",
    ):
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    data = (
        _resolve_duplicate_prices(data)
        .sort_values(["stock_code", "trade_date"])
        .reset_index(drop=True)
    )
    grouped = data.groupby("stock_code", sort=False)
    close = grouped["close_price"]
    volume = grouped["volume"]

    data["return_1d"] = close.pct_change(fill_method=None)
    for horizon in (5, 20, 60, 120):
        data[f"momentum_{horizon}d"] = (
            data["close_price"] / close.shift(horizon) - 1.0
        )
    for window in (5, 20, 60):
        data[f"sma_{window}d"] = close.transform(
            lambda values, window=window: values.rolling(
                window, min_periods=window
            ).mean()
        )

    data["price_to_sma_20d"] = data["close_price"] / data["sma_20d"] - 1.0
    data["volatility_20d"] = grouped["return_1d"].transform(
        lambda values: values.rolling(20, min_periods=20).std() * math.sqrt(252)
    )
    data["volatility_60d"] = grouped["return_1d"].transform(
        lambda values: values.rolling(60, min_periods=60).std() * math.sqrt(252)
    )
    data["volume_sma_20d"] = volume.transform(
        lambda values: values.rolling(20, min_periods=20).mean()
    )
    data["volume_ratio_20d"] = data["volume"] / data["volume_sma_20d"].replace(
        0, np.nan
    )

    if "trading_value" in data:
        data["trading_value_sma_20d"] = grouped["trading_value"].transform(
            lambda values: values.rolling(20, min_periods=20).mean()
        )
    if "market_cap" in data:
        data["log_market_cap"] = np.log(
            data["market_cap"].where(data["market_cap"] > 0)
        )

    # Target은 Feature가 아니며 학습 입력 컬럼에서 반드시 제외한다.
    for horizon in (5, 20):
        data[f"target_date_{horizon}d"] = grouped["trade_date"].shift(-horizon)
        data[f"target_return_{horizon}d"] = (
            close.shift(-horizon) / data["close_price"] - 1.0
        )
    data["target_up_20d"] = (data["target_return_20d"] > 0).astype("Int8")
    data.loc[data["target_return_20d"].isna(), "target_up_20d"] = pd.NA
    data["history_120d_ready"] = data["momentum_120d"].notna()
    return data


def assign_purged_time_split(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """시간순 70/15/15 분할 후 Target horizon이 경계를 넘는 행을 학습 제외 표시한다."""

    data = frame.copy()
    dates = pd.Index(sorted(data["trade_date"].dropna().unique()))
    if len(dates) < 30:
        raise RuntimeError("not enough unique trade dates for temporal split")

    train_end = pd.Timestamp(dates[int(len(dates) * 0.70) - 1])
    validation_end = pd.Timestamp(dates[int(len(dates) * 0.85) - 1])
    test_end = pd.Timestamp(dates[-1])

    data["split"] = "test"
    data.loc[data["trade_date"] <= train_end, "split"] = "train"
    data.loc[
        (data["trade_date"] > train_end)
        & (data["trade_date"] <= validation_end),
        "split",
    ] = "validation"

    split_end = data["split"].map(
        {
            "train": train_end,
            "validation": validation_end,
            "test": test_end,
        }
    )
    for horizon in (5, 20):
        data[f"eligible_target_{horizon}d"] = data[
            f"target_date_{horizon}d"
        ].notna() & (data[f"target_date_{horizon}d"] <= split_end)

    return data, {
        "train_end": train_end.date().isoformat(),
        "validation_end": validation_end.date().isoformat(),
        "test_end": test_end.date().isoformat(),
        "split_method": "chronological_70_15_15_with_target_horizon_purge",
    }


assign_time_split = assign_purged_time_split


def compute_market_features(frame: pd.DataFrame) -> pd.DataFrame:
    """시장지수별 추세·모멘텀·변동성 Feature를 만든다."""

    required = {"trade_date", "index_name", "close_index"}
    missing = required - set(frame)
    if missing:
        raise ValueError(f"market index processed columns missing: {sorted(missing)}")

    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce")
    data["close_index"] = pd.to_numeric(data["close_index"], errors="coerce")
    data = data.sort_values(["index_name", "trade_date"]).reset_index(drop=True)
    grouped = data.groupby("index_name", sort=False)

    data["index_return_1d"] = grouped["close_index"].pct_change(fill_method=None)
    data["index_momentum_20d"] = (
        data["close_index"] / grouped["close_index"].shift(20) - 1.0
    )
    data["index_sma_20d"] = grouped["close_index"].transform(
        lambda values: values.rolling(20, min_periods=20).mean()
    )
    data["index_above_sma_20d"] = data["close_index"] > data["index_sma_20d"]
    data["index_volatility_20d"] = grouped["index_return_1d"].transform(
        lambda values: values.rolling(20, min_periods=20).std() * math.sqrt(252)
    )
    return data


def compute_latest_security_master(frame: pd.DataFrame) -> pd.DataFrame:
    """종목별 가장 최근 기준정보를 제공하되 역사적 유니버스 판단에는 사용하지 않는다."""

    required = {
        "reference_date",
        "stock_code",
        "isin_code",
        "stock_name",
        "market_category",
        "corporation_number",
    }
    missing = required - set(frame)
    if missing:
        raise ValueError(f"security master processed columns missing: {sorted(missing)}")

    data = frame.copy()
    data["reference_date"] = pd.to_datetime(data["reference_date"], errors="coerce")
    data["stock_code"] = data["stock_code"].astype("string")
    data["corporation_number"] = data["corporation_number"].astype("string")
    data = data.sort_values(["stock_code", "reference_date"])
    latest = data.drop_duplicates("stock_code", keep="last").reset_index(drop=True)
    latest["usage_warning"] = (
        "latest reference only; do not use for historical universe membership"
    )
    return latest


def compute_financial_features(frame: pd.DataFrame) -> pd.DataFrame:
    """재무 Snapshot에 구조적 재무비율을 추가한다.

    base_date는 공시가 실제로 시장에 알려진 시각을 보장하지 않으므로 이 결과는 가격 데이터와
    자동 결합하지 않는다.
    """

    data = frame.copy()
    if "base_date" in data:
        data["base_date"] = pd.to_datetime(data["base_date"], errors="coerce")
    if "corporation_number" in data:
        data["corporation_number"] = data["corporation_number"].astype("string")
    for column in (
        "sales",
        "operating_profit",
        "net_income",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "capital",
        "reported_debt_ratio_pct",
        "comprehensive_income",
    ):
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    if {"total_liabilities", "total_equity"} <= set(data):
        data["debt_to_equity"] = data["total_liabilities"] / data[
            "total_equity"
        ].replace(0, np.nan)
        data["debt_ratio_pct_calculated"] = data["debt_to_equity"] * 100.0
    if {"net_income", "total_assets"} <= set(data):
        data["roa"] = data["net_income"] / data["total_assets"].replace(0, np.nan)
    if {"net_income", "total_equity"} <= set(data):
        data["roe"] = data["net_income"] / data["total_equity"].replace(0, np.nan)
    if {"operating_profit", "sales"} <= set(data):
        data["operating_margin"] = data["operating_profit"] / data["sales"].replace(
            0, np.nan
        )
    if {"net_income", "sales"} <= set(data):
        data["net_margin"] = data["net_income"] / data["sales"].replace(0, np.nan)

    data["point_in_time_join_ready"] = False
    return data


def compute_financial_company_year_latest(frame: pd.DataFrame) -> pd.DataFrame:
    """회사/사업연도/재무구분별 최신 Snapshot과 YoY를 연구용으로 만든다.

    최신 Snapshot 선택 자체가 미래시점 정보를 사용할 수 있으므로 가격 예측 학습에 직접 JOIN하면
    안 된다. OpenDART 접수일 등 실제 availability date를 붙인 뒤 point-in-time 변환해야 한다.
    """

    data = compute_financial_features(frame)
    required = {
        "corporation_number",
        "business_year",
        "financial_division_code",
        "base_date",
    }
    if not required <= set(data):
        raise ValueError(
            f"financial annual snapshot columns missing: {sorted(required - set(data))}"
        )

    data["business_year"] = pd.to_numeric(data["business_year"], errors="coerce")
    key = ["corporation_number", "business_year", "financial_division_code"]
    annual = (
        data.sort_values(key + ["base_date"])
        .drop_duplicates(key, keep="last")
        .sort_values(["corporation_number", "financial_division_code", "business_year"])
        .reset_index(drop=True)
    )
    grouped = annual.groupby(
        ["corporation_number", "financial_division_code"], sort=False
    )
    for column in ("sales", "operating_profit", "net_income"):
        if column in annual:
            previous = grouped[column].shift(1)
            annual[f"{column}_growth_yoy"] = annual[column] / previous.replace(0, np.nan) - 1.0
    annual["research_only"] = True
    annual["point_in_time_join_ready"] = False
    return annual


def _write_monthly(
    storage,
    container: str,
    dataset: str,
    frame: pd.DataFrame,
    date_column: str,
    version: str,
    metadata: dict[str, str],
    overwrite: bool,
) -> list[dict[str, Any]]:
    """Feature Dataset을 날짜 기준 월별 Parquet으로 저장한다."""

    data = frame.copy()
    data[date_column] = pd.to_datetime(data[date_column], errors="coerce")
    data = data.loc[data[date_column].notna()].copy()
    data["_year"] = data[date_column].dt.year
    data["_month"] = data[date_column].dt.month
    outputs: list[dict[str, Any]] = []

    for (year, month), monthly in data.groupby(["_year", "_month"], sort=True):
        output = monthly.drop(columns=["_year", "_month"]).reset_index(drop=True)
        path = (
            f"{dataset}/version=v{version}/year={int(year):04d}/"
            f"month={int(month):02d}/part-00000.parquet"
        )
        with tempfile.TemporaryDirectory(prefix="fein-feature-") as directory:
            local = Path(directory) / "part-00000.parquet"
            output.to_parquet(local, index=False, compression="zstd")
            result = storage.upload_file(
                container,
                path,
                local,
                content_type="application/vnd.apache.parquet",
                overwrite=overwrite,
                metadata={**metadata, "record_count": str(len(output))},
            )
        outputs.append({"path": path, "rows": len(output), "bytes": result.size})
        print(f"FEATURE WRITE dataset={dataset} rows={len(output)} path={path}")
    return outputs


def build_model_datasets(
    storage,
    *,
    processed_container: str,
    features_container: str,
    schema_version: str = "1",
    feature_version: str = "1",
    overwrite: bool = False,
) -> dict[str, Any]:
    """학습 가능 Dataset과 시점 확인이 필요한 연구용 Dataset을 함께 생성한다."""

    git_sha = os.getenv("GIT_SHA", "unknown")
    result: dict[str, Any] = {}

    stock, split = assign_purged_time_split(
        compute_stock_features(
            load_processed_operation(
                storage,
                processed_container,
                "stock_price",
                "getstockpriceinfo",
                schema_version,
            )
        )
    )
    result["model_stock_daily"] = {
        "status": "training_ready",
        "files": _write_monthly(
            storage,
            features_container,
            "model_stock_daily",
            stock,
            "trade_date",
            feature_version,
            {
                "layer": "features",
                "dataset": "model_stock_daily",
                "feature_version": feature_version,
                "processed_schema_version": schema_version,
                "git_sha": git_sha,
                "training_ready": "true",
            },
            overwrite,
        ),
        "rows": len(stock),
        "split": split,
    }

    market = compute_market_features(
        load_processed_operation(
            storage,
            processed_container,
            "market_index",
            "getstockmarketindex",
            schema_version,
        )
    )
    result["market_index_daily"] = {
        "status": "training_ready",
        "files": _write_monthly(
            storage,
            features_container,
            "market_index_daily",
            market,
            "trade_date",
            feature_version,
            {
                "layer": "features",
                "dataset": "market_index_daily",
                "feature_version": feature_version,
                "processed_schema_version": schema_version,
                "git_sha": git_sha,
                "training_ready": "true",
            },
            overwrite,
        ),
        "rows": len(market),
    }

    master = compute_latest_security_master(
        load_processed_operation(
            storage,
            processed_container,
            "stock_master",
            "getiteminfo",
            schema_version,
        )
    )
    result["security_master_latest"] = {
        "status": "reference_only",
        "files": _write_monthly(
            storage,
            features_container,
            "security_master_latest",
            master,
            "reference_date",
            feature_version,
            {
                "layer": "features",
                "dataset": "security_master_latest",
                "feature_version": feature_version,
                "processed_schema_version": schema_version,
                "git_sha": git_sha,
                "training_ready": "false",
            },
            overwrite,
        ),
        "rows": len(master),
    }

    financial_source = load_processed_operation(
        storage,
        processed_container,
        "financial_statement",
        "getsummfinastat_v2",
        schema_version,
    )
    financial = compute_financial_features(financial_source)
    result["financial_snapshot"] = {
        "status": "research_only_until_availability_date",
        "files": _write_monthly(
            storage,
            features_container,
            "financial_snapshot",
            financial,
            "base_date",
            feature_version,
            {
                "layer": "features",
                "dataset": "financial_snapshot",
                "feature_version": feature_version,
                "processed_schema_version": schema_version,
                "git_sha": git_sha,
                "point_in_time_join": "not_ready",
                "training_ready": "false",
            },
            overwrite,
        ),
        "rows": len(financial),
        "point_in_time_join_ready": False,
    }

    annual = compute_financial_company_year_latest(financial_source)
    result["financial_company_year_latest"] = {
        "status": "research_only_until_availability_date",
        "files": _write_monthly(
            storage,
            features_container,
            "financial_company_year_latest",
            annual,
            "base_date",
            feature_version,
            {
                "layer": "features",
                "dataset": "financial_company_year_latest",
                "feature_version": feature_version,
                "processed_schema_version": schema_version,
                "git_sha": git_sha,
                "point_in_time_join": "not_ready",
                "training_ready": "false",
            },
            overwrite,
        ),
        "rows": len(annual),
        "point_in_time_join_ready": False,
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feature_version": feature_version,
        "processed_schema_version": schema_version,
        "git_sha": git_sha,
        "look_ahead_policy": (
            "financial datasets are not joined to market data until an actual "
            "publication/availability timestamp is resolved"
        ),
        **result,
    }
    storage.upload_bytes(
        features_container,
        f"_manifests/model-datasets/version=v{feature_version}/manifest.json",
        json.dumps(payload, ensure_ascii=False, indent=2).encode(),
        content_type="application/json",
        overwrite=True,
    )
    return payload
