"""Deterministic low-volatility and momentum stock selectors."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RuleSelectionConfig:
    top_n: int = 10
    universe_size: int = 100
    min_trading_value: float = 0.0

    def __post_init__(self) -> None:
        if self.top_n <= 0 or self.universe_size < self.top_n:
            raise ValueError("universe_size must be at least top_n and both must be positive")
        if self.min_trading_value < 0:
            raise ValueError("min_trading_value cannot be negative")


class FactorRuleRanker:
    """Rank one or more point-in-time cross-sections without future data."""

    def __init__(self, factor: str, config: RuleSelectionConfig = RuleSelectionConfig()) -> None:
        if factor not in {"low_volatility", "momentum"}:
            raise ValueError(f"unsupported factor: {factor}")
        self.factor = factor
        self.config = config

    @property
    def score_column(self) -> str:
        return "volatility_60d" if self.factor == "low_volatility" else "momentum_120d"

    def rank(self, frame: pd.DataFrame) -> pd.DataFrame:
        required = {"trade_date", "stock_code", "market_cap", self.score_column}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"rule model columns missing: {missing}")
        data = frame.copy()
        data["trade_date"] = pd.to_datetime(data["trade_date"], errors="raise")
        data["stock_code"] = data["stock_code"].astype("string")
        for column in ("market_cap", self.score_column):
            data[column] = pd.to_numeric(data[column], errors="coerce")
        if "trading_value_sma_20d" in data:
            data["trading_value_sma_20d"] = pd.to_numeric(
                data["trading_value_sma_20d"], errors="coerce"
            )
        else:
            data["trading_value_sma_20d"] = float("inf")

        data = data.loc[
            data["market_cap"].gt(0)
            & data[self.score_column].notna()
            & data["trading_value_sma_20d"].ge(self.config.min_trading_value)
        ].copy()
        data = (
            data.sort_values(
                ["trade_date", "market_cap", "stock_code"],
                ascending=[True, False, True],
            )
            .groupby("trade_date", group_keys=False)
            .head(self.config.universe_size)
        )
        ascending = self.factor == "low_volatility"
        data["rank"] = data.groupby("trade_date")[self.score_column].rank(
            method="first", ascending=ascending
        ).astype("Int64")
        data["score"] = (
            -data[self.score_column] if ascending else data[self.score_column]
        )
        data["selected"] = data["rank"].le(self.config.top_n)
        return data.sort_values(["trade_date", "rank", "stock_code"]).reset_index(drop=True)


class LowVolatilityRanker(FactorRuleRanker):
    def __init__(self, config: RuleSelectionConfig = RuleSelectionConfig()) -> None:
        super().__init__("low_volatility", config)


class MomentumRanker(FactorRuleRanker):
    def __init__(self, config: RuleSelectionConfig = RuleSelectionConfig()) -> None:
        super().__init__("momentum", config)