"""Point-in-time risk-adjusted momentum factor model."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

COMMON_SPLIT_RATIOS = (0.1, 0.2, 0.25, 1 / 3, 0.5, 2.0, 3.0, 4.0, 5.0, 10.0)


@dataclass(frozen=True)
class RiskAdjustedMomentumConfig:
    """Public-institution-inspired momentum settings without claiming index replication."""

    skip_trading_days: int = 21
    six_month_trading_days: int = 126
    twelve_month_trading_days: int = 252
    weekly_volatility_observations: int = 156
    corporate_action_share_change: float = 0.10
    split_market_value_tolerance: float = 0.30
    split_ratio_tolerance: float = 0.01
    non_disruptive_price_return: float = 0.30
    winsor_limit: float = 3.0
    universe_size: int = 100
    selection_fraction: float = 0.20
    min_positions: int = 19
    max_positions: int = 20

    def __post_init__(self) -> None:
        if min(
            self.skip_trading_days,
            self.six_month_trading_days,
            self.twelve_month_trading_days,
            self.weekly_volatility_observations,
            self.universe_size,
            self.min_positions,
            self.max_positions,
        ) <= 0:
            raise ValueError("momentum windows and portfolio sizes must be positive")
        if self.six_month_trading_days >= self.twelve_month_trading_days:
            raise ValueError("six-month window must be shorter than twelve-month window")
        if not 0 < self.corporate_action_share_change < 1:
            raise ValueError("corporate action share-change threshold must be in (0, 1)")
        if not 0 < self.split_market_value_tolerance < 1:
            raise ValueError("split market-value tolerance must be in (0, 1)")
        if not 0 < self.split_ratio_tolerance < 1:
            raise ValueError("split ratio tolerance must be in (0, 1)")
        if not 0 < self.non_disruptive_price_return < 1:
            raise ValueError("non-disruptive price return must be in (0, 1)")
        if self.winsor_limit <= 0:
            raise ValueError("winsor_limit must be positive")
        if not 0 < self.selection_fraction <= 1:
            raise ValueError("selection_fraction must be in (0, 1]")
        if self.min_positions > self.max_positions or self.max_positions > 20:
            raise ValueError("position bounds must be ordered and Backend-compatible")


def _weekly_volatility(group: pd.DataFrame, observations: int) -> pd.Series:
    """Use only completed week-end observations available on each decision date."""

    dated = group.set_index("trade_date")["close_price"]
    weekly_close = dated.resample("W-FRI").last().dropna()
    weekly_volatility = (
        weekly_close.pct_change(fill_method=None)
        .rolling(observations, min_periods=observations)
        .std()
        * math.sqrt(52)
    )
    available = pd.DataFrame(
        {"available_date": weekly_volatility.index, "value": weekly_volatility.values}
    ).dropna()
    if available.empty:
        return pd.Series(np.nan, index=group.index, dtype=float)
    aligned = pd.merge_asof(
        group[["trade_date"]].reset_index(),
        available,
        left_on="trade_date",
        right_on="available_date",
        direction="backward",
    ).set_index("index")
    return aligned["value"].reindex(group.index)


def _cross_sectional_zscore(values: pd.Series) -> pd.Series:
    valid = pd.to_numeric(values, errors="coerce")
    deviation = float(valid.std(ddof=0))
    if not math.isfinite(deviation) or deviation <= 0:
        return pd.Series(np.nan, index=values.index, dtype=float)
    return (valid - float(valid.mean())) / deviation


class RiskAdjustedMomentumModel:
    """Compute and rank 6M/12M skip-one-month risk-adjusted momentum."""

    MODEL_VERSION = "risk-adjusted-momentum-v2"

    def __init__(
        self, config: RiskAdjustedMomentumConfig = RiskAdjustedMomentumConfig()
    ) -> None:
        self.config = config

    def compute_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        required = {
            "stock_code",
            "trade_date",
            "close_price",
            "listed_shares",
            "market_cap",
        }
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"risk-adjusted momentum columns missing: {missing}")
        data = frame.copy()
        data["stock_code"] = data["stock_code"].astype("string")
        data["trade_date"] = pd.to_datetime(data["trade_date"], errors="raise")
        if data[["stock_code", "trade_date"]].isna().any(axis=None):
            raise ValueError("trade_date and stock_code cannot be null")
        if data.duplicated(["stock_code", "trade_date"]).any():
            raise ValueError("duplicate trade_date + stock_code rows are not allowed")
        for column in ("close_price", "listed_shares", "market_cap"):
            data[column] = pd.to_numeric(data[column], errors="coerce")
        data = data.sort_values(["stock_code", "trade_date"]).reset_index(drop=True)

        pieces: list[pd.DataFrame] = []
        config = self.config
        six_offset = config.skip_trading_days + config.six_month_trading_days
        twelve_offset = config.skip_trading_days + config.twelve_month_trading_days
        volatility_days = config.weekly_volatility_observations * 5
        for _, group in data.groupby("stock_code", sort=False):
            group = group.copy()
            close = group["close_price"]
            shares = group["listed_shares"]
            price_ratio = close / close.shift(1)
            share_ratio = shares / shares.shift(1)
            share_event = (share_ratio - 1.0).abs().gt(
                config.corporate_action_share_change
            )
            non_disruptive = (price_ratio - 1.0).abs().le(
                config.non_disruptive_price_return
            )
            split_ratio_like = pd.concat(
                [
                    (share_ratio / ratio - 1.0).abs()
                    for ratio in COMMON_SPLIT_RATIOS
                ],
                axis=1,
            ).min(axis=1).le(config.split_ratio_tolerance)
            split_like = split_ratio_like & (
                (price_ratio * share_ratio - 1.0).abs().le(
                    config.split_market_value_tolerance
                )
            )
            valid_inputs = close.gt(0) & shares.gt(0)
            event_safe = valid_inputs & (~share_event | non_disruptive | split_like)
            adjustment_applied = share_event & ~non_disruptive & split_like
            adjustment_multiplier = share_ratio.where(adjustment_applied, 1.0)
            group["corporate_action_event"] = share_event
            group["corporate_action_event_safe"] = event_safe
            group["split_ratio_like"] = split_ratio_like
            group["price_adjustment_applied"] = adjustment_applied
            # 과거 가격을 미래 기업행위로 back-adjust하지 않는다. 이벤트 당일 확인된
            # 주식수 비율만 이후 가격에 누적해 point-in-time 가격 축을 유지한다.
            group["point_in_time_adjusted_close"] = close * adjustment_multiplier.cumprod()
            adjusted_close = group["point_in_time_adjusted_close"]
            endpoint = adjusted_close.shift(config.skip_trading_days)
            group["return_6m_skip1m"] = endpoint / adjusted_close.shift(six_offset) - 1.0
            group["return_12m_skip1m"] = endpoint / adjusted_close.shift(twelve_offset) - 1.0

            unsafe = (~event_safe).astype(float)
            group["corporate_action_safe_6m"] = (
                unsafe.shift(config.skip_trading_days)
                .rolling(config.six_month_trading_days + 1, min_periods=config.six_month_trading_days + 1)
                .max()
                .eq(0.0)
            )
            group["corporate_action_safe_12m"] = (
                unsafe.shift(config.skip_trading_days)
                .rolling(config.twelve_month_trading_days + 1, min_periods=config.twelve_month_trading_days + 1)
                .max()
                .eq(0.0)
            )
            group["corporate_action_safe_volatility"] = (
                unsafe.rolling(volatility_days, min_periods=volatility_days)
                .max()
                .eq(0.0)
            )
            weekly_group = group.copy()
            weekly_group["close_price"] = weekly_group["point_in_time_adjusted_close"]
            group["volatility_3y_weekly"] = _weekly_volatility(
                weekly_group, config.weekly_volatility_observations
            )
            pieces.append(group)

        data = pd.concat(pieces, ignore_index=True)
        if "annual_risk_free_rate" in data:
            annual_rate = pd.to_numeric(data["annual_risk_free_rate"], errors="coerce")
            if annual_rate.isna().any() or annual_rate.le(-1).any():
                raise ValueError("annual_risk_free_rate must be complete and greater than -1")
            data["risk_free_return_6m"] = (1.0 + annual_rate) ** (
                config.six_month_trading_days / 252
            ) - 1.0
            data["risk_free_return_12m"] = (1.0 + annual_rate) ** (
                config.twelve_month_trading_days / 252
            ) - 1.0
            data["risk_free_policy"] = "point_in_time_annual_rate"
        else:
            # Azure macro에는 KOFR 등 단기 무위험금리가 없으므로 기준금리/3년물을
            # 대용하지 않고 원수익률을 유지한다. 이는 상수 금리 가정이 아니라 중립 정책이다.
            data["risk_free_return_6m"] = 0.0
            data["risk_free_return_12m"] = 0.0
            data["risk_free_policy"] = "neutral_no_short_rate_available"

        volatility = data["volatility_3y_weekly"].where(
            data["volatility_3y_weekly"].gt(0)
        )
        data["risk_adjusted_momentum_6m"] = (
            data["return_6m_skip1m"] - data["risk_free_return_6m"]
        ) / volatility
        data["risk_adjusted_momentum_12m"] = (
            data["return_12m_skip1m"] - data["risk_free_return_12m"]
        ) / volatility
        data["v2_history_ready"] = (
            data[[
                "return_6m_skip1m",
                "return_12m_skip1m",
                "volatility_3y_weekly",
            ]].notna().all(axis=1)
            & data["volatility_3y_weekly"].gt(0)
        )
        data["corporate_action_safe"] = data[[
            "corporate_action_safe_6m",
            "corporate_action_safe_12m",
            "corporate_action_safe_volatility",
        ]].all(axis=1)
        return data

    def rank(self, frame: pd.DataFrame) -> pd.DataFrame:
        required = {
            "trade_date",
            "stock_code",
            "market_cap",
            "risk_adjusted_momentum_6m",
            "risk_adjusted_momentum_12m",
            "v2_history_ready",
            "corporate_action_safe",
        }
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"risk-adjusted ranking columns missing: {missing}")
        data = frame.copy()
        eligible = data["v2_history_ready"].fillna(False).astype(bool) & data[
            "corporate_action_safe"
        ].fillna(False).astype(bool)
        if "is_tradable" in data:
            eligible &= data["is_tradable"].fillna(False).astype(bool)
        if "risk_eligible" in data:
            eligible &= data["risk_eligible"].fillna(False).astype(bool)
        data = data.loc[eligible & pd.to_numeric(data["market_cap"], errors="coerce").gt(0)].copy()
        data = (
            data.sort_values(["trade_date", "market_cap", "stock_code"], ascending=[True, False, True])
            .groupby("trade_date", group_keys=False)
            .head(self.config.universe_size)
        )
        data["zscore_6m"] = data.groupby("trade_date", group_keys=False)[
            "risk_adjusted_momentum_6m"
        ].transform(_cross_sectional_zscore).clip(-self.config.winsor_limit, self.config.winsor_limit)
        data["zscore_12m"] = data.groupby("trade_date", group_keys=False)[
            "risk_adjusted_momentum_12m"
        ].transform(_cross_sectional_zscore).clip(-self.config.winsor_limit, self.config.winsor_limit)
        data["combined_z_raw"] = 0.5 * data["zscore_6m"] + 0.5 * data["zscore_12m"]
        data["combined_z"] = data.groupby("trade_date", group_keys=False)[
            "combined_z_raw"
        ].transform(_cross_sectional_zscore).clip(-self.config.winsor_limit, self.config.winsor_limit)
        data["rank"] = data.groupby("trade_date")["combined_z"].rank(
            method="first", ascending=False
        ).astype("Int64")
        count = data.groupby("trade_date")["stock_code"].transform("size")
        # 결정 rank에서 직접 파생해 winsor 동률에서도 score/rank 순서가 어긋나지 않는다.
        data["momentum_score"] = (count - data["rank"].astype(int) + 1) / count
        data["score"] = data["momentum_score"]
        selected_count = np.ceil(count * self.config.selection_fraction).astype(int)
        selected_count = selected_count.clip(
            lower=self.config.min_positions, upper=self.config.max_positions
        ).clip(upper=count)
        data["selected"] = data["rank"].le(selected_count)
        return data.sort_values(["trade_date", "rank", "stock_code"]).reset_index(drop=True)
