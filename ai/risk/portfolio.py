"""Long-only portfolio construction with explicit P0 constraints."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PortfolioConstraints:
    max_positions: int = 10
    max_weight: float = 0.15
    cash_buffer: float = 0.05
    max_turnover: float = 0.30
    min_trade_weight: float = 0.005

    def __post_init__(self) -> None:
        if self.max_positions <= 0:
            raise ValueError("max_positions must be positive")
        if not 0 < self.max_weight <= 1:
            raise ValueError("max_weight must be in (0, 1]")
        if not 0 <= self.cash_buffer < 1:
            raise ValueError("cash_buffer must be in [0, 1)")
        if not 0 <= self.max_turnover <= 2:
            raise ValueError("max_turnover must be in [0, 2]")
        if not 0 <= self.min_trade_weight <= 1:
            raise ValueError("min_trade_weight must be in [0, 1]")
        if self.max_positions * self.max_weight < 1 - self.cash_buffer:
            raise ValueError("position limits cannot deploy the requested invested weight")


def _normalize_capped_equal_weight(codes: list[str], constraints: PortfolioConstraints) -> pd.Series:
    invested = 1.0 - constraints.cash_buffer
    if not codes:
        return pd.Series(dtype=float)
    weight = invested / len(codes)
    if weight > constraints.max_weight + 1e-12:
        raise ValueError("selected positions cannot satisfy max_weight")
    return pd.Series(weight, index=codes, dtype=float)


def construct_portfolio(
    candidates: pd.DataFrame,
    *,
    current_weights: pd.Series | None = None,
    constraints: PortfolioConstraints = PortfolioConstraints(),
) -> pd.DataFrame:
    """Convert ranked eligible stocks to weights and cap one-way turnover."""

    required = {"stock_code", "score"}
    missing = sorted(required - set(candidates.columns))
    if missing:
        raise ValueError(f"portfolio candidate columns missing: {missing}")
    data = candidates.copy()
    if "risk_eligible" in data:
        data = data.loc[data["risk_eligible"].fillna(False).astype(bool)]
    data["score"] = pd.to_numeric(data["score"], errors="coerce")
    selected = (
        data.loc[data["score"].notna()]
        .sort_values(["score", "stock_code"], ascending=[False, True])
        .drop_duplicates("stock_code")
        .head(constraints.max_positions)
    )
    target = _normalize_capped_equal_weight(selected["stock_code"].astype(str).tolist(), constraints)

    current = pd.Series(dtype=float) if current_weights is None else pd.Series(current_weights, dtype=float)
    if (current < 0).any() or current.sum() > 1 + 1e-9:
        raise ValueError("current weights must be long-only and sum to at most one")
    all_codes = current.index.union(target.index)
    current = current.reindex(all_codes, fill_value=0.0)
    target = target.reindex(all_codes, fill_value=0.0)
    delta = target - current
    delta = delta.where(delta.abs().ge(constraints.min_trade_weight), 0.0)
    turnover = float(delta.abs().sum() / 2.0)
    if turnover > constraints.max_turnover and turnover > 0:
        delta *= constraints.max_turnover / turnover
    final = (current + delta).clip(lower=0.0, upper=constraints.max_weight)
    result = pd.DataFrame({"stock_code": final.index.astype(str), "weight": final.values})
    result = result.loc[result["weight"].gt(0)].sort_values(
        ["weight", "stock_code"], ascending=[False, True]
    )
    result["cash_weight"] = max(0.0, 1.0 - float(result["weight"].sum()))
    return result.reset_index(drop=True)
