"""Point-in-time tradability and stock-level risk filters."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class StockRiskConfig:
    min_price: float = 1_000.0
    min_market_cap: float = 0.0
    min_trading_value_20d: float = 0.0
    max_volatility_60d: float = 1.0
    max_volume_ratio_20d: float = 10.0
    require_history_120d: bool = True

    def __post_init__(self) -> None:
        if self.min_price < 0 or self.min_market_cap < 0 or self.min_trading_value_20d < 0:
            raise ValueError("minimum thresholds cannot be negative")
        if self.max_volatility_60d <= 0 or self.max_volume_ratio_20d <= 0:
            raise ValueError("maximum thresholds must be positive")


def apply_stock_risk_filter(
    frame: pd.DataFrame,
    config: StockRiskConfig = StockRiskConfig(),
) -> pd.DataFrame:
    """Annotate eligibility and stable rejection reasons without dropping audit rows."""

    required = {
        "stock_code",
        "trade_date",
        "close_price",
        "market_cap",
        "trading_value_sma_20d",
        "volatility_60d",
        "volume_ratio_20d",
        "history_120d_ready",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"stock risk columns missing: {missing}")
    data = frame.copy()
    for column in (
        "close_price",
        "market_cap",
        "trading_value_sma_20d",
        "volatility_60d",
        "volume_ratio_20d",
    ):
        data[column] = pd.to_numeric(data[column], errors="coerce")

    reasons: list[str] = []
    eligible: list[bool] = []
    for row in data.itertuples(index=False):
        failures: list[str] = []
        if pd.isna(row.close_price) or row.close_price < config.min_price:
            failures.append("price")
        if pd.isna(row.market_cap) or row.market_cap < config.min_market_cap:
            failures.append("market_cap")
        if pd.isna(row.trading_value_sma_20d) or row.trading_value_sma_20d < config.min_trading_value_20d:
            failures.append("liquidity")
        if pd.isna(row.volatility_60d) or row.volatility_60d > config.max_volatility_60d:
            failures.append("volatility")
        if pd.isna(row.volume_ratio_20d) or row.volume_ratio_20d > config.max_volume_ratio_20d:
            failures.append("abnormal_volume")
        if config.require_history_120d and (
            pd.isna(row.history_120d_ready) or not bool(row.history_120d_ready)
        ):
            failures.append("history")
        eligible.append(not failures)
        reasons.append("eligible" if not failures else ",".join(failures))
    data["risk_eligible"] = eligible
    data["risk_reason"] = reasons
    return data
