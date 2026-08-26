"""Leakage-safe Ridge and LightGBM cross-sectional ranking models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lightgbm import LGBMRegressor
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from models.contracts import (
    DEFAULT_FEATURE_COLUMNS,
    RankingPrediction,
    rank_predictions,
    validate_feature_columns,
    validate_panel,
)


@dataclass(frozen=True)
class RankerConfig:
    feature_columns: tuple[str, ...] = DEFAULT_FEATURE_COLUMNS
    target_column: str = "target_return_20d"
    random_state: int = 42

    def __post_init__(self) -> None:
        validate_feature_columns(self.feature_columns)
        if not self.target_column.startswith("target_"):
            raise ValueError("target_column must be explicitly named as a target")


class BaseMLRanker:
    model_name = "base"

    def __init__(self, config: RankerConfig = RankerConfig()) -> None:
        self.config = config
        self.estimator: Any = None
        self.fitted_through: pd.Timestamp | None = None

    def _build_estimator(self) -> Any:
        raise NotImplementedError

    def fit(self, frame: pd.DataFrame, *, training_end: str | pd.Timestamp) -> "BaseMLRanker":
        cutoff = pd.Timestamp(training_end)
        data = validate_panel(
            frame,
            self.config.feature_columns,
            target_column=self.config.target_column,
            require_target=True,
        )
        data = data.loc[data["trade_date"].le(cutoff)].copy()
        target_date_column = self.config.target_column.replace("return_", "date_")
        if target_date_column in data:
            target_dates = pd.to_datetime(data[target_date_column], errors="coerce")
            data = data.loc[target_dates.le(cutoff)].copy()
        eligible_column = self.config.target_column.replace("target_return_", "eligible_target_")
        if eligible_column in data:
            data = data.loc[data[eligible_column].fillna(False).astype(bool)].copy()
        data = data.loc[data[self.config.target_column].notna()]
        if data.empty:
            raise ValueError("no eligible training rows remain before training_end")

        self.estimator = self._build_estimator()
        self.estimator.fit(
            data.loc[:, self.config.feature_columns],
            data[self.config.target_column],
        )
        self.fitted_through = cutoff
        return self

    def predict(self, frame: pd.DataFrame) -> RankingPrediction:
        if self.estimator is None or self.fitted_through is None:
            raise RuntimeError("ranker must be fitted before prediction")
        data = validate_panel(frame, self.config.feature_columns)
        if data["trade_date"].le(self.fitted_through).any():
            raise ValueError("prediction rows must be strictly after the training cutoff")
        scores = self.estimator.predict(data.loc[:, self.config.feature_columns])
        return rank_predictions(data, np.asarray(scores), self.model_name)


class RidgeStockRanker(BaseMLRanker):
    model_name = "ridge"

    def __init__(self, config: RankerConfig = RankerConfig(), *, alpha: float = 1.0) -> None:
        super().__init__(config)
        if alpha < 0:
            raise ValueError("alpha cannot be negative")
        self.alpha = alpha

    def _build_estimator(self) -> Pipeline:
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", Ridge(alpha=self.alpha)),
            ]
        )


class LightGBMStockRanker(BaseMLRanker):
    model_name = "lightgbm"

    def __init__(
        self,
        config: RankerConfig = RankerConfig(),
        **model_params: Any,
    ) -> None:
        super().__init__(config)
        self.model_params = model_params

    def _build_estimator(self) -> LGBMRegressor:
        params = {
            "objective": "regression",

            "n_estimators": 200,
            "learning_rate": 0.03,
            "num_leaves": 15,
            "max_depth": 5,
            "min_child_samples": 30,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "random_state": self.config.random_state,
            "n_jobs": -1,
            "verbosity": -1,
                }
        params.update(self.model_params)
        return LGBMRegressor(**params)