"""Single source of truth for Momentum v2 input features."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def add_momentum_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the live Momentum v2 features without imputing source values.

    Input columns use the canonical lower-case names shared by the database
    and Data pipeline.  ``is_tradable`` follows the algorithm OHLCV quality
    contract and deliberately does not inspect ``trading_value``.
    """

    required = {"stock_code", "trade_date", "close_price", "volume"}
    missing = required - set(frame)
    if missing:
        raise ValueError(f"momentum feature columns missing: {sorted(missing)}")
    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="raise")
    for column in ("open_price", "high_price", "low_price"):
        if column not in data:
            data[column] = np.nan
    data = data.sort_values(["stock_code", "trade_date"]).reset_index(drop=True)
    grouped = data.groupby("stock_code", sort=False)
    close = grouped["close_price"]
    volume = grouped["volume"]
    data["return_1d"] = close.pct_change(fill_method=None)
    data["momentum_120d"] = data["close_price"] / close.shift(120) - 1.0
    data["volatility_60d"] = grouped["return_1d"].transform(
        lambda values: values.rolling(60, min_periods=60).std() * math.sqrt(252)
    )
    volume_sma = volume.transform(lambda values: values.rolling(20, min_periods=20).mean())
    data["volume_ratio_20d"] = data["volume"] / volume_sma.replace(0, np.nan)
    if "trading_value" in data:
        data["trading_value_sma_20d"] = grouped["trading_value"].transform(
            lambda values: values.rolling(20, min_periods=20).mean()
        )
    else:
        data["trading_value_sma_20d"] = np.nan
    data["history_120d_ready"] = data["close_price"].notna() & close.shift(120).notna()

    intraday = data[["open_price", "high_price", "low_price"]]
    prices = data[["open_price", "high_price", "low_price", "close_price"]]
    positive_prices = prices.notna().all(axis=1) & prices.gt(0).all(axis=1)
    no_intraday_price = intraday.notna().all(axis=1) & intraday.eq(0).all(axis=1)
    partial_non_positive_ohl = (intraday.notna() & intraday.le(0)).any(axis=1) & ~no_intraday_price
    inconsistent_ohlc = positive_prices & (
        data["high_price"].lt(data["low_price"])
        | data["high_price"].lt(data["open_price"])
        | data["high_price"].lt(data["close_price"])
        | data["low_price"].gt(data["open_price"])
        | data["low_price"].gt(data["close_price"])
    )
    missing_ohlcv = data[["volume", "open_price", "high_price", "low_price", "close_price"]].isna().any(axis=1)
    data["is_tradable"] = ~(
        missing_ohlcv
        | (data["close_price"].notna() & data["close_price"].le(0))
        | (data["volume"].notna() & data["volume"].lt(0))
        | no_intraday_price
        | partial_non_positive_ohl
        | inconsistent_ohlc
    )
    return data
