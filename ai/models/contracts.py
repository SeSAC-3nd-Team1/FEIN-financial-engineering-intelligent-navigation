"""Shared contracts and leakage guards for stock-ranking models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

KEY_COLUMNS = ("trade_date", "stock_code")
DEFAULT_FEATURE_COLUMNS = (
    "momentum_5d",
    "momentum_20d",
    "momentum_60d",
    "momentum_120d",
    "price_to_sma_20d",
    "volatility_20d",
    "volatility_60d",
    "volume_ratio_20d",
    "trading_value_sma_20d",
    "log_market_cap",
)
LEAKAGE_PREFIXES = ("target_", "eligible_target_")
LEAKAGE_COLUMNS = {"split"}


@dataclass(frozen=True)
class RankingPrediction:
    """One out-of-sample score and within-date rank per security."""

    frame: pd.DataFrame
    model_name: str


def validate_feature_columns(feature_columns: Iterable[str]) -> tuple[str, ...]:
    columns = tuple(feature_columns)
    if not columns:
        raise ValueError("at least one feature column is required")
    if len(set(columns)) != len(columns):
        raise ValueError("feature columns must be unique")
    forbidden = [
        column
        for column in columns
        if column in LEAKAGE_COLUMNS or column.startswith(LEAKAGE_PREFIXES)
    ]
    if forbidden:
        raise ValueError(f"target or split columns cannot be model features: {forbidden}")
    return columns


def validate_panel(
    frame: pd.DataFrame,
    feature_columns: Iterable[str],
    *,
    target_column: str | None = None,
    require_target: bool = False,
) -> pd.DataFrame:
    """Normalize keys/numerics and reject duplicate point-in-time observations."""

    features = validate_feature_columns(feature_columns)
    required = set(KEY_COLUMNS) | set(features)
    if require_target and target_column:
        required.add(target_column)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"model columns missing: {missing}")

    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="raise")
    data["stock_code"] = data["stock_code"].astype("string")
    if data[list(KEY_COLUMNS)].isna().any(axis=None):
        raise ValueError("trade_date and stock_code cannot be null")
    if data.duplicated(list(KEY_COLUMNS)).any():
        raise ValueError("duplicate trade_date + stock_code rows are not allowed")

    numeric_columns = list(features)
    if target_column and target_column in data:
        numeric_columns.append(target_column)
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
        data[column] = data[column].replace([np.inf, -np.inf], np.nan)
    return data.sort_values(list(KEY_COLUMNS)).reset_index(drop=True)


def rank_predictions(data: pd.DataFrame, scores: np.ndarray, model_name: str) -> RankingPrediction:
    if len(data) != len(scores):
        raise ValueError("prediction count must match input rows")
    result = data.loc[:, list(KEY_COLUMNS)].copy()
    result["score"] = np.asarray(scores, dtype=float)
    result["rank"] = result.groupby("trade_date")["score"].rank(
        method="first", ascending=False
    ).astype("Int64")
    return RankingPrediction(result, model_name)