"""Deterministic market-regime baseline for strategy risk control."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import pandas as pd


class MarketRegime(StrEnum):
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"


@dataclass(frozen=True)
class RegimeConfig:
    high_volatility: float = 0.25
    positive_momentum: float = 0.0

    def __post_init__(self) -> None:
        if self.high_volatility <= 0:
            raise ValueError("high_volatility must be positive")


class RuleBasedRegimeModel:
    """Classify each index observation using only same-day precomputed features."""

    def __init__(self, config: RegimeConfig = RegimeConfig()) -> None:
        self.config = config

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        required = {
            "trade_date",
            "index_above_sma_20d",
            "index_momentum_20d",
            "index_volatility_20d",
        }
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"market regime columns missing: {missing}")
        data = frame.copy()
        data["trade_date"] = pd.to_datetime(data["trade_date"], errors="raise")
        for column in ("index_momentum_20d", "index_volatility_20d"):
            data[column] = pd.to_numeric(data[column], errors="coerce")

        unavailable = data[["index_above_sma_20d", "index_momentum_20d", "index_volatility_20d"]].isna().any(axis=1)
        risk_off = (
            ~data["index_above_sma_20d"].eq(True)
            | data["index_momentum_20d"].lt(self.config.positive_momentum)
            | data["index_volatility_20d"].ge(self.config.high_volatility)
        )
        risk_on = (
            data["index_above_sma_20d"].eq(True)
            & data["index_momentum_20d"].ge(self.config.positive_momentum)
            & data["index_volatility_20d"].lt(self.config.high_volatility)
        )
        data["regime"] = MarketRegime.NEUTRAL.value
        data.loc[risk_on & ~unavailable, "regime"] = MarketRegime.RISK_ON.value
        data.loc[risk_off & ~unavailable, "regime"] = MarketRegime.RISK_OFF.value
        return data.sort_values("trade_date").reset_index(drop=True)